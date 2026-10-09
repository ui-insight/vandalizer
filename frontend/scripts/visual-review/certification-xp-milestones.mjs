import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const modules = JSON.parse(await readFile(new URL('panel-modules.json', data), 'utf8'))
const structure = JSON.parse(await readFile(new URL('course-structure.json', data), 'utf8'))
const identity = { enrollment_id: 'qa-xp-milestones', course_version: 'qa-milestones', manifest_sha256: 'd'.repeat(64), course_title: 'XP milestone display preview', modules_total: modules.length, module_ids: modules.map(item => item.id), maximum_xp: 1850 }
const course = { ...structure, ...identity, versioned: true, modules, prerequisites: Object.fromEntries(modules.map(item => [item.id, []])) }
const progress = { ...identity, id: 'qa-milestones', user_id: 'reviewer', modules: {}, total_xp: 150, level: 'novice', certified: false, learning_position: null, position_revision: 0 }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual milestone disclosure with synthetic course/progress. Standard and unknown long level names, keyboard expansion, element bounds and large XP values. No real enrollment or credit.' })
const { page, context } = review
const before = structuredClone(progress)
await context.route('**/api/certification/**', route => {
  const req = route.request(), path = new URL(req.url()).pathname
  assert.equal(req.method(), 'GET', `Unexpected certification write ${path}`)
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  return route.fallback()
})
async function capture(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const kind of ['standard', 'custom']) {
    course.levels = kind === 'standard' ? structure.levels : [...structure.levels, { name: 'Independent agent supervision and evidence verification milestone', xp: 123456789 }]
    for (const width of native ? [640, 780, 1440] : [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: native ? 1000 : 650 })
      await page.goto(review.baseURL + '/certification')
      if (native) await review.setBrowserZoom(2)
      const panel = page.locator('[data-cert-panel="true"]')
      await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
      const summary = panel.locator('summary').filter({ hasText: /^XP milestones$/ })
      const details = summary.locator('..')
      assert.equal(await details.getAttribute('open'), null)
      await summary.focus(); await page.keyboard.press('Enter')
      await details.locator('ul').waitFor()
      const list = details.getByRole('list', { name: 'XP milestones', exact: true })
      assert.equal(await list.getByRole('listitem').count(), course.levels.length)
      assert.equal(await list.getByText(/· Reached$/).count(), 2)
      assert.equal(await list.getByText(/· Not reached$/).count(), course.levels.length - 2)
      await details.getByText('XP milestones are separate from course completion. Certification requires completing the course’s required module checks.', { exact: true }).waitFor()
      await capture(`${kind}-expanded-${width}`)
      const metrics = await list.evaluate(el => [...el.querySelectorAll('li')].map(item => {
        const bounds = item.getBoundingClientRect()
        return { noHorizontalOverflow: item.scrollWidth <= item.clientWidth, inPage: bounds.left >= 0 && bounds.right <= innerWidth, text: [...item.querySelectorAll('span')].map(span => ({ size: parseFloat(getComputedStyle(span).fontSize), value: span.textContent })) }
      }))
      for (const metric of metrics) {
        assert.equal(metric.noHorizontalOverflow, true); assert.equal(metric.inPage, true)
        assert.ok(metric.text.every(text => text.size >= 12))
      }
      const last = list.getByRole('listitem').last()
      await last.scrollIntoViewIfNeeded()
      assert.equal(await last.evaluate(el => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight }), true)
      if (kind === 'custom') await last.getByText('123,456,789 XP · Not reached', { exact: true }).waitFor()
      await capture(`${kind}-last-reachable-${width}`)
      await summary.focus(); await page.keyboard.press('Space')
      assert.equal(await details.getAttribute('open'), null)
      await capture(`${kind}-collapsed-focus-${width}`)
      review.observations.push({ kind, width, milestoneMetrics: metrics, keyboardToggle: true })
    }
  }
  assert.deepEqual(progress, before)
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ certificationWrites: 0, unchangedProgress: true, realCreditAwarded: false })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
