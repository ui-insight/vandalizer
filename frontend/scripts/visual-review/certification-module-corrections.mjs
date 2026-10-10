import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const fixture = JSON.parse(await readFile(process.env.REVIEW_FIXTURE, 'utf8'))
const identity = { ...fixture.course, enrollment_id: 'a'.repeat(32) }
const progress = { ...identity, id: 'qa-module-corrections', user_id: 'reviewer', modules: {},
  learning_position: null, position_revision: 0, total_xp: 0, level: 'novice', certified: false, certified_at: null }
const course = { ...identity, versioned: true, progress,
  prerequisites: Object.fromEntries(identity.modules.map(module => [module.id, []])) }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL,
  evidenceMode: 'Frozen course with actual read-only API correction projection; synthetic transport, no learner writes.' })
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
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1600 : 1000 })
    for (const moduleId of ['governance', 'ai_literacy']) {
      const module = identity.modules.find(item => item.id === moduleId)
      await page.goto(review.baseURL + '/certification')
      if (native) await review.setBrowserZoom(2)
      const panel = page.locator('[data-cert-panel]')
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      await panel.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
      const note = panel.getByRole('complementary', { name: module.editorialNotices[0].title })
      const description = panel.getByText(module.description, { exact: true })
      await note.waitFor()
      assert.equal(await note.evaluate(element => {
        const sibling = element.nextElementSibling
        return sibling?.tagName === 'P' && !!(element.compareDocumentPosition(sibling) & Node.DOCUMENT_POSITION_FOLLOWING)
      }), true)
      assert.equal(await description.count(), 1)
      for (const [suffix, target] of [['guidance', note.getByText(module.editorialNotices[0].title, { exact: true })],
        ['preserved-description', description]]) {
        await target.scrollIntoViewIfNeeded()
        const id = `${moduleId}-${suffix}-${width}`
        await review.capture(id)
        assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
        assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
        console.log(id)
      }
    }
  }
  assert.deepEqual(writes, []); assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ courseWrites: writes, preservedDescriptions: true, correctionsBeforeDescriptions: true,
    manifestSha256: identity.manifest_sha256, moduleIds: ['governance', 'ai_literacy'], assessedRequirementsChanged: false })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
