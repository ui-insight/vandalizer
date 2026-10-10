import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const fixture = JSON.parse(await readFile(process.env.REVIEW_FIXTURE, 'utf8'))
const working = process.env.REVIEW_WORKING_TEACHING === '1'
const modules = working ? JSON.parse(await readFile(new URL('../../../backend/certification-data/panel-modules.json', import.meta.url), 'utf8')) : fixture.course.modules
const moduleIds = (process.env.REVIEW_MODULES || 'foundations,process_mapping,workflow_design,extraction_engine,multi_step,advanced_nodes,validation_qa,batch_processing,governance').split(',')
assert.ok(moduleIds.every(id => modules.some(module => module.id === id)))
const identity = { ...fixture.course, modules, enrollment_id: 'a'.repeat(32), ...(working ? { manifest_sha256: 'd'.repeat(64), course_version: 'qa-working-guidance' } : {}) }
const progress = { ...identity, id: 'qa-module-guidance', user_id: 'reviewer', modules: {}, learning_position: null, position_revision: 0, total_xp: 0, level: 'novice', certified: false, certified_at: null }
const course = { ...identity, versioned: true, progress, prerequisites: Object.fromEntries(modules.map(module => [module.id, []])) }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL, evidenceMode: 'Current metadata or actual frozen-course projection via synthetic transport. No lab, learner or assessment writes.' })
const { page, context } = review
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
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1600 : 1000 })
    for (const moduleId of moduleIds) {
      const module = modules.find(item => item.id === moduleId)
      await page.goto(review.baseURL + '/certification')
      if (native) await review.setBrowserZoom(2)
      const panel = page.locator('[data-cert-panel]')
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      await panel.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
      const description = panel.getByText(module.description, { exact: true })
      if (!working) {
        const correction = module.editorialNotices.find(note => note.id === moduleId + '-module-hints-2026-10-09.1')
        assert.ok(correction)
        const note = panel.getByRole('complementary', { name: correction.title, exact: true })
        await note.waitFor()
        if (process.env.REVIEW_TEXT_SCALE === '2' && width <= 390) {
          assert.ok((await note.locator('p').first().boundingBox()).width >= 220, 'Enlarged correction text must not be squeezed by nested padding')
        }
        assert.equal(await note.evaluate((element, text) => {
          const paragraph = [...element.parentElement.querySelectorAll('p')].find(item => item.textContent === text)
          return !!paragraph && !!(element.compareDocumentPosition(paragraph) & Node.DOCUMENT_POSITION_FOLLOWING)
        }, module.description), true)
        await capture(`${moduleId}-guidance-${width}`, note)
      } else await capture(`${moduleId}-description-${width}`, description)
      await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
      const tips = panel.getByRole('button', { name: 'Tips & Hints', exact: true })
      await tips.focus()
      assert.equal(await tips.getAttribute('aria-expanded'), 'false')
      await page.keyboard.press('Enter')
      assert.equal(await tips.getAttribute('aria-expanded'), 'true')
      const list = panel.locator(`#${await tips.getAttribute('aria-controls')}`)
      for (const tip of module.tips) assert.equal(await list.getByText(tip, { exact: true }).count(), 1)
      if (!working) assert.equal(await panel.getByRole('complementary', { name: 'Current guidance for ' + module.title, exact: true }).count(), 1)
      await capture(`${moduleId}-tips-${width}`, list)
      await tips.focus(); await page.keyboard.press('Enter')
      assert.equal(await tips.getAttribute('aria-expanded'), 'false')
      assert.equal(await list.count(), 0)
    }
  }
  assert.deepEqual(writes, []); assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ moduleIds, working, keyboardTipDisclosure: true, preservedHistoricalTips: !working, courseWrites: writes, assessmentChanged: false })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
