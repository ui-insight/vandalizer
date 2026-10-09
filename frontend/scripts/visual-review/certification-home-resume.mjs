import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const modules = JSON.parse(await readFile(new URL('panel-modules.json', data), 'utf8')).slice(0, 2)
const identity = { enrollment_id: 'qa-selected-course', course_version: 'qa-two-module-course', manifest_sha256: 'a'.repeat(64), course_title: 'Selected course — QA fixture', modules_total: 2, module_ids: modules.map(m => m.id), maximum_xp: 300 }
let progress = { ...identity, id: 'qa-progress', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false,
  learning_position: { module_id: modules[0].id, lesson_id: modules[0].lessons[1].id, revision: 1, content_sha256: 'b'.repeat(64), saved_at: '2026-10-05T00:00:00Z' } }
const course = { ...identity, versioned: true, modules, prerequisites: {}, levels: [], tiers: [] }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5292' })
const { page, context } = review
const writes = []
await context.route('**/api/certification/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (request.method() !== 'GET') writes.push(path)
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  return route.fallback()
})
try {
  for (const completed of [false, true]) {
    if (completed) progress = { ...progress, modules: { ai_literacy: { completed: true }, retired_module: { completed: true } } }
    for (const width of [320, 1440]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
      await page.goto(review.baseURL)
      const cta = page.getByRole('button', { name: `Continue certification (${completed ? 1 : 0}/2)`, exact: true })
      await cta.scrollIntoViewIfNeeded()
      await review.capture(`home-${completed ? 'selected-credit' : 'saved-place'}-${width}`, 'Synthetic selected course verifies its own module count and continuation before first completion. Existing chat kickoff behavior is unchanged.')
      assert.equal(await page.getByRole('button', { name: 'Start the certification course', exact: true }).count(), 0)
    }
  }
  assert.deepEqual(writes, [])
  assert.deepEqual([...review.unmatched], [])
  assert.deepEqual(review.errors, [])
  for (const capture of review.captures) {
    assert.equal(capture.pageWidth, capture.viewport.width)
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/${capture.id}.axe.json`, 'utf8')), [])
  }
} catch (error) { await review.capture('blocked'); throw error } finally { await review.flush(); await review.browser.close() }
