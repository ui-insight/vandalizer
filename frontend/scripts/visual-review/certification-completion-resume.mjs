import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json'), structure = await read('course-structure.json')
const identity = { enrollment_id: 'qa-completion-enrollment', course_version: 'qa-completion-course', manifest_sha256: 'b'.repeat(64), course_title: 'Preserved course — QA fixture', modules_total: modules.length, module_ids: modules.map(m => m.id), maximum_xp: 2675 }
const course = { ...identity, ...structure, versioned: true, prerequisites: Object.fromEntries(modules.map(m => [m.id, []])), modules }
const progress = { ...identity, learning_position: null, position_revision: 0, id: 'qa-progress', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, last_activity_date: null, pending_completions: [] }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5305', resetStorage: false })
const { page, context } = review
let reads = 0
const writes = []
await context.route('**/api/certification/**', async route => {
  const path = new URL(route.request().url()).pathname
  if (route.request().method() !== 'GET') writes.push(path)
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress')) { reads++; return route.fulfill({ json: progress }) }
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id) {
  await review.capture(id, 'Actual frozen frontend; synthetic unresolved completion states. No grading, credit, support message or other write is dispatched.')
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 960 : 480 })
    for (const state of ['uncertain', 'evaluating', 'review']) {
      progress.pending_completions = (state === 'uncertain' ? modules : [modules[1]]).map((m, i) => ({ attempt_id: (i + 1).toString(16).padStart(32, '0'), module_id: m.id, state, in_flight: state === 'evaluating' }))
      await page.goto(review.baseURL + '/certification')
      if (native) await review.setBrowserZoom(2)
      await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      const notice = page.getByRole('region', { name: 'Pending certification completion', exact: true })
      await notice.waitFor()
      if (state === 'uncertain') {
        const lastRefresh = notice.getByRole('button', { name: 'Refresh status', exact: true }).last()
        await lastRefresh.focus()
        const visible = await lastRefresh.evaluate(el => {
          const r = el.getBoundingClientRect(), parent = el.closest('section').getBoundingClientRect()
          return r.top >= parent.top && r.bottom <= Math.min(parent.bottom, innerHeight) && parent.bottom < innerHeight - 100
        })
        await capture(`many-pending-${native ? 'native' : width}`)
        assert.ok(visible, 'The last pending action must be reachable while leaving usable course space')
      } else {
        assert.equal(await notice.getByRole('button', { name: 'Resume original completion', exact: true }).count(), 0)
        await capture(`${state}-${native ? 'native' : width}`)
      }
      const before = reads
      await notice.getByRole('button', { name: 'Refresh status', exact: true }).last().click()
      await page.waitForTimeout(100)
      assert.ok(reads > before)
      assert.deepEqual(writes, [])
    }
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ shortViewport: true, multiplePendingModules: true, keyboardReachable: true, refreshReadOnly: true })
} catch (error) { await capture('blocked'); throw error } finally { await review.flush(); await review.browser.close() }
