import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const modules = JSON.parse(await readFile('../backend/certification-data/panel-modules.json', 'utf8')).slice(0, 2)
const identity = { enrollment_id: 'qa-retained-course', course_version: 'qa-original-course', manifest_sha256: 'a'.repeat(64),
  course_title: 'Retained original course — QA', module_ids: modules.map(module => module.id), modules_total: modules.length }
const course = { ...identity, versioned: true, modules, prerequisites: Object.fromEntries(modules.map(module => [module.id, []])),
  levels: [{ name: 'novice', xp: 0 }], tiers: [{ name: 'Original course', theme: 'Retained work', narrative: 'Original requirements.', moduleIds: modules.map(module => module.id), celebration: 'Review saved work.' }] }
let progress
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5340',
  evidenceMode: 'Production chat failure recovery with synthetic unavailable/denied/interrupted responses and retained course. No provider, grading or actual learner write.' })
const { page, context, state } = review
const reads = [], writes = [], chats = []
await context.route('**/api/config/models', route => route.fulfill({ json: [] }))
await context.route('**/api/config/user', route => route.fulfill({ json: { model: null, temperature: 0.2, top_p: 1, available_models: [] } }))
await context.route('**/api/chat', route => { chats.push(route.request().postDataJSON()); return route.fallback() })
await context.route('**/api/certification/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (path.endsWith('/journey-events')) return route.fallback()
  if (request.method() === 'GET') reads.push(path)
  else writes.push(path)
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
const cases = [
  { id: 'start-unavailable', prompt: 'Start the Vandalizer certification course — show me where to begin.', error: 'The selected model is unavailable. Choose another model or try again later.', code: 'model_unavailable', course: true },
  { id: 'continue-denied', prompt: 'Continue my certification — show my progress and the next module.', error: 'This chat capability is unavailable for your current access.', code: 'forbidden', course: true, active: true },
  { id: 'course-tool-interrupted', prompt: 'What should I do next?', error: 'The response could not finish. Check saved work before retrying.', code: 'interrupted', course: true, active: true, tool: true },
  { id: 'unrelated-chat', prompt: 'Summarize certification requirements in this grant.', error: 'The selected model is unavailable. Choose another model or try again later.', code: 'model_unavailable', course: false },
]
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded(); await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [640] : [320, 1440]) for (const sample of native ? cases.slice(0, 1) : cases) {
    const savedPosition = sample.active ? { module_id: modules[0].id, lesson_id: modules[0].lessons[1].id, revision: 1, content_sha256: 'b'.repeat(64), saved_at: '2026-10-05T00:00:00Z' } : null
    progress = { ...identity, id: 'qa-progress', user_id: 'reviewer', modules: savedPosition ? { [modules[0].id]: { completed: false, stars: 0, xp_earned: 0, attempts: 0, learning_position: savedPosition } } : {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: savedPosition }
    const original = JSON.stringify(progress)
    await page.setViewportSize({ width, height: native ? 2200 : 1100 })
    await page.goto(review.baseURL)
    if (native) await review.setBrowserZoom(2)
    state.chatChunks = [...(sample.tool ? [{ kind: 'tool_call', tool_name: 'get_certification_progress', tool_call_id: 'course-read', args: {} }] : []), { kind: 'error', content: sample.error, code: sample.code }]
    const beforeChat = chats.length
    const composer = page.getByRole('textbox', { name: 'Message input', exact: true })
    await composer.fill(sample.prompt)
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    const alert = page.getByRole('alert').filter({ hasText: sample.error })
    await alert.waitFor()
    const button = alert.getByRole('button', { name: 'Open course without chat', exact: true })
    assert.equal(await button.count(), sample.course ? 1 : 0)
    await capture(`${sample.id}-error-${width}`, alert)
    if (sample.course) {
      await composer.fill('Keep this next question unsent.')
      const beforeRead = reads.length
      await button.focus(); await page.keyboard.press('Enter')
      const panel = page.locator('[data-cert-panel]')
      await panel.waitFor()
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      assert.ok(reads.length > beforeRead)
      const moduleButton = panel.getByRole('button', { name: /^(?:0 )?AI Literacy/ })
      if (await moduleButton.count()) await moduleButton.click()
      const lesson = panel.getByRole('heading', { name: modules[0].lessons[sample.active ? 1 : 0].title, exact: true })
      await lesson.waitFor()
      await capture(`${sample.id}-course-${width}`, lesson)
      await page.keyboard.press('Escape')
      assert.equal(await composer.inputValue(), 'Keep this next question unsent.')
    }
    assert.equal(chats.length, beforeChat + 1)
    assert.equal(JSON.stringify(progress), original)
    review.observations.push({ case: sample.id, width, courseRecovery: sample.course, freshReadOnlyRefresh: sample.course, automaticChatRetries: 0, originalProgressPreserved: true })
  }
  assert.deepEqual(writes, []); assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
