import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const modules = JSON.parse(await readFile('../backend/certification-data/panel-modules.json', 'utf8')).slice(0, 2)
const identity = { enrollment_id: 'qa-selected-course', course_version: 'qa-original-course', manifest_sha256: 'a'.repeat(64),
  course_title: 'Selected original course — QA', module_ids: modules.map(module => module.id), modules_total: modules.length, maximum_xp: modules.reduce((sum, module) => sum + module.xp, 0) }
const course = { ...identity, versioned: true, modules, prerequisites: Object.fromEntries(modules.map(module => [module.id, []])),
  levels: [{ name: 'novice', xp: 0 }, { name: 'apprentice', xp: 100 }],
  tiers: [{ name: 'Selected course', theme: 'Original requirements', narrative: 'Retained course for direct navigation QA.', moduleIds: modules.map(module => module.id), celebration: 'Review your retained course.' }] }
let progress
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5307',
  evidenceMode: 'Production home and learning panel with synthetic selected-course states and no configured models. Direct navigation only; no chat request, assessment or credit write.' })
const { page, context, state } = review
const writes = [], chatRequests = []
await context.route('**/api/config/models', route => route.fulfill({ json: [] }))
await context.route('**/api/config/user', route => route.fulfill({ json: { model: null, temperature: 0.2, top_p: 1, available_models: [] } }))
await context.route('**/api/chat**', route => { if (route.request().method() !== 'GET') chatRequests.push(route.request().url()); return route.fallback() })
await context.route('**/api/certification/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (request.method() !== 'GET') writes.push(path)
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded(); await review.capture(id)
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1688 : 1000 })
    for (const home of ['first', 'returning']) for (const kind of ['new', 'active', 'completed']) {
      state.first = home === 'first'
      const completed = kind === 'completed'
      progress = { ...identity, id: 'qa-progress', user_id: 'reviewer', modules: completed ? Object.fromEntries(modules.map(module => [module.id, { completed: true, stars: 1, xp_earned: module.xp, attempts: 1 }])) : {},
        total_xp: completed ? identity.maximum_xp : 0, level: 'novice', certified: completed, certified_at: completed ? '2026-10-01T00:00:00Z' : null,
        learning_position: kind === 'active' ? { module_id: modules[0].id, lesson_id: modules[0].lessons[1].id, revision: 1, content_sha256: 'b'.repeat(64), saved_at: '2026-10-05T00:00:00Z' } : null }
      if (progress.learning_position) progress.modules[modules[0].id] = { completed: false, stars: 0, xp_earned: 0, attempts: 0, learning_position: progress.learning_position }
      await page.goto(review.baseURL)
      if (native) await review.setBrowserZoom(2)
      const button = page.getByRole('button', { name: completed ? 'Review completed course' : 'Open course without chat', exact: true })
      await button.waitFor()
      await capture(`${home}-${kind}-entry-${width}`, button)
      await button.focus(); await page.keyboard.press('Enter')
      const panel = page.locator('[data-cert-panel]')
      await panel.waitFor()
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      await capture(`${home}-${kind}-panel-${width}`, panel)
      const moduleButton = panel.getByRole('button', { name: /^(?:0 )?AI Literacy/ })
      if (await moduleButton.count()) await moduleButton.click()
      const lesson = panel.getByRole('heading', { name: modules[0].lessons[kind === 'active' ? 1 : 0].title, exact: true })
      await lesson.waitFor()
      await capture(`${home}-${kind}-lesson-${width}`, lesson)
      await page.keyboard.press('Escape')
      assert.equal(await page.getByRole('textbox', { name: 'Message input', exact: true }).inputValue(), '')
    }
  }
  assert.deepEqual(writes, [])
  assert.deepEqual(chatRequests, [])
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ homeStates: ['first', 'returning'], courseStates: ['new', 'active', 'completed'], configuredModels: 0, courseWrites: writes, chatRequests, keyboardOpen: true })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
