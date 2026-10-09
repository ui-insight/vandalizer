import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual frontend with synthetic API fixtures; panel bounds, keyboard navigation and unsent chat preservation. Viewport contraction is not an actual mobile keyboard.' })
const { page, context } = review
const writes = []
await context.route('**/api/certification/**', async route => {
  if (route.request().method() !== 'GET') writes.push(new URL(route.request().url()).pathname)
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
const baseline = process.env.REVIEW_BASELINE === '1'
const panel = page.locator('[data-cert-panel]')
const position = page.getByRole('combobox', { name: 'Learning panel position', exact: true })
const close = page.getByRole('button', { name: 'Return to workspace', exact: true })
async function openPanel() {
  const opener = page.getByRole('button', { name: 'Open learning panel', exact: true })
  if (!await opener.isVisible()) {
    const activity = page.getByRole('button', { name: 'Open activity', exact: true })
    await activity.focus(); await page.keyboard.press('Enter')
  }
  await opener.focus(); await page.keyboard.press('Enter')
  await panel.waitFor()
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
  assert.equal(await panel.evaluate(el => el.contains(document.activeElement)), true, 'Opening the course moves focus into it, including from the activity drawer')
}
async function capture(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  const bounds = await panel.evaluate(el => { const r = el.getBoundingClientRect(); return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: innerWidth, height: innerHeight } })
  const contained = bounds.left >= -1 && bounds.top >= -1 && bounds.right <= bounds.width + 1 && bounds.bottom <= bounds.height + 1
  review.observations.push({ id, bounds, contained })
  if (!baseline) assert.equal(contained, true, `${id}: entire panel must remain in the viewport`)
  console.log(id, JSON.stringify(bounds))
}
async function dragToEdge() {
  const title = panel.getByText('Certification', { exact: true })
  const box = await title.boundingBox()
  const viewport = await page.evaluate(() => ({ width: innerWidth, height: innerHeight }))
  await page.mouse.move(box.x + 10, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(viewport.width - 1, viewport.height - 1, { steps: 8 })
  await page.mouse.up()
}
try {
  await page.goto(review.baseURL)
  if (native) await review.setBrowserZoom(2)
  const draft = page.getByRole('textbox', { name: 'Message input', exact: true })
  await draft.fill('Unsent learner question — keep my current work.')
  await openPanel()
  await position.selectOption('floating')
  await dragToEdge()
  await capture('floating-drag-edge')
  // A real layout viewport resize after dragging must re-clamp saved coordinates.
  await page.setViewportSize({ width: native ? 780 : 390, height: native ? 500 : 250 })
  await capture('floating-after-contraction')
  for (const mode of ['docked-bottom', 'docked-left', 'docked-right', 'fullscreen', 'floating']) {
    // Baseline intentionally may have controls offscreen; selecting is a
    // diagnostic only. Fixed runs assert the close action is reachable.
    await position.selectOption(mode)
    await capture(`short-${mode}`)
    if (!baseline) {
      await close.focus()
      assert.equal(await close.evaluate(el => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth }), true)
      if (mode === 'fullscreen') {
        await page.keyboard.press('Shift+Tab')
        assert.equal(await panel.evaluate(el => el.contains(document.activeElement)), true, 'Modal focus stays in the panel')
      } else {
        await close.focus(); await page.keyboard.press('Shift+Tab')
        assert.equal(await panel.evaluate(el => el.contains(document.activeElement)), false, 'A nonmodal panel permits keyboard return to workspace')
      }
      await close.focus(); await page.keyboard.press('Escape')
      await panel.waitFor({ state: 'hidden' })
      await page.waitForFunction(() => ['Open learning panel', 'Open activity', 'Expand activity'].includes(document.activeElement?.getAttribute('aria-label')))
      assert.equal(await draft.inputValue(), 'Unsent learner question — keep my current work.')
      await openPanel()
    }
  }
  assert.deepEqual(writes, [])
  assert.deepEqual([...review.unmatched], []); assert.deepEqual(review.errors, [])
} catch (error) {
  review.observations.push({ failure: String(error), activeElement: await page.evaluate(() => document.activeElement?.outerHTML) })
  await review.capture('blocked', String(error))
  throw error
} finally { await review.flush(); await review.browser.close() }
