import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5294',
  evidenceMode: 'Synthetic lifecycle presentation only; actual completion and closed-state protections are verified separately with disposable MongoDB.' })
const { page, context } = review
let lifecycle = 'completed'
const enrollment = 'a'.repeat(32)
const labels = { completed: 'Recorded as completed.', transferred: 'Closed transfer history.', abandoned: 'Closed course history.' }
const reads = []
await context.route('**/api/certification/practical-history**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  assert.equal(request.method(), 'GET'); reads.push(path)
  const identity = { enrollment_id: enrollment, course_version: 'original-course-2026.1', course_title: 'Original certification course', enrollment_state: lifecycle, selection_status: 'retained' }
  return route.fulfill({ json: path.endsWith('/practical-history') ? { read_only: true, older_courses_available: false,
    courses: [{ ...identity, definition_available: true, created_at: null }] } : { ...identity, manifest_sha256: 'b'.repeat(64), read_only: true, modules: [] } })
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    for (const state of Object.keys(labels)) {
      lifecycle = state
      await page.goto(review.baseURL + '/certification')
      if (native) await review.setBrowserZoom(2)
      const panel = page.locator('[data-cert-panel="true"]')
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      await panel.getByText('Course progress and credential', { exact: true }).click()
      await panel.getByRole('button', { name: 'Browse saved course work', exact: true }).click()
      await panel.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(enrollment)
      const region = panel.getByRole('region', { name: 'Original course history', exact: true })
      await region.getByText(new RegExp(labels[state])).waitFor()
      await region.scrollIntoViewIfNeeded()
      const id = `${state}-${native ? 'native' : width}`
      await review.capture(id)
      assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
      const shot = review.captures.at(-1), box = await region.boundingBox()
      assert.equal(shot.pageWidth, shot.viewport.width)
      assert.ok(box.x >= 0 && box.x + box.width <= shot.viewport.width)
      console.log(id)
    }
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ lifecycleAndSelectionLabelsSeparate: true, historyReadsOnly: reads.length })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
