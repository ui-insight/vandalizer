import assert from 'node:assert/strict'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT || '../artifacts/visual-review/recovery-layout', baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5183' })
const { page, state } = review
page.setDefaultTimeout(9000)
async function go(path) { await page.goto(review.baseURL + path); await page.getByRole('main').waitFor(); await page.waitForTimeout(500) }
async function shot(id) { await review.capture(id); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${id}: overflow`) }
async function reachable(locator) {
  await locator.scrollIntoViewIfNeeded()
  const box = await locator.boundingBox(); const viewport = page.viewportSize()
  assert.ok(box && box.y >= 0 && box.y + box.height <= viewport.height && box.x >= 0 && box.x + box.width <= viewport.width, 'Primary action stays reachable')
}
try {
  state.catalogLong = true; state.catalogScenario = true
  state.optimization = true; state.validationQueries = true
  for (const [width, height] of [[320,568],[768,600],[1440,900]]) {
    await page.setViewportSize({ width, height })
    await go('/?mode=chat&tab=library')
    await page.getByRole('button', { name: 'Explore', exact: true }).click()
    await page.getByPlaceholder('Search items...').fill('Proposal')
    await page.getByRole('button').filter({ hasText: 'Proposal readiness review' }).click()
    await shot(`catalog-long-detail-${width}`)
    await reachable(page.getByRole('button', { name: 'Save to Library', exact: true }))
    await shot(`catalog-long-detail-actions-${width}`)
    await page.getByRole('button', { name: 'Save to Library', exact: true }).click()
    await page.getByRole('button', { name: 'Save', exact: true }).waitFor()
    await reachable(page.getByRole('button', { name: 'Save', exact: true }))
    await shot(`catalog-save-dialog-${width}`)
    await page.getByRole('button', { name: 'Cancel', exact: true }).click()
    await page.getByRole('dialog').waitFor()
    await page.keyboard.press('Escape')
    assert.equal(await page.getByPlaceholder('Search items...').inputValue(), 'Proposal')

    await go('/?mode=knowledge')
    await page.getByRole('button', { name: 'Edit', exact: true }).click()
    await page.getByRole('tab', { name: 'Validation', exact: true }).click()
    await page.getByRole('tab', { name: 'Improve retrieval', exact: true }).click()
    await page.getByRole('button', { name: 'Apply optimized settings', exact: true }).click()
    const dialog=page.getByRole('dialog')
    await reachable(dialog.getByRole('checkbox'))
    await dialog.getByRole('checkbox').check()
    await reachable(dialog.getByRole('button', { name: 'Apply', exact: true }))
    await shot(`validation-confirm-actions-${width}`)
    await page.keyboard.press('Escape')
    await page.getByRole('button', { name: /Reproducibility/ }).click()
    await page.getByText('Judge model', { exact: true }).scrollIntoViewIfNeeded()
    await shot(`validation-provenance-${width}`)
  }
} catch (error) {
  review.errors.push(String(error)); await review.capture('layout-blocked', String(error)); process.exitCode = 1
} finally {
  await review.flush(); await review.browser.close()
  if (review.errors.length || review.unmatched.size) process.exitCode = 1
  console.log(JSON.stringify({ captures: review.captures.length, errors: review.errors, unmatched: [...review.unmatched] }, null, 2))
}
