import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { catalog } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(10000)
let entry
await page.route('**/api/verification/verified?*', route => route.fulfill({ json: { items: [entry], total: 1 } }))
const variants = [
  ['measured', { quality_score: 0, quality_tier: 'fair', last_validated_at: '2026-09-01T10:00:00Z', test_case_count: 12 }, 'Recorded validation score'],
  ['unmeasured', { quality_score: null, quality_tier: null, last_validated_at: null, test_case_count: undefined, validation_run_count: 0 }, 'No measured score available'],
  ['asserted', { quality_score: null, quality_tier: 'excellent', quality_asserted: true, last_validated_at: null, validation_run_count: 0 }, 'Author-provided rating; not measured here'],
  ['regression', { regression_pending_review: true }, 'Recorded validation score'],
]
try {
  for (const [width,height] of [[320,568],[768,600],[1440,900]]) {
    await page.setViewportSize({width,height})
    for (const [name, overrides, origin] of variants) {
      entry = { ...catalog[0], ...overrides }
      await page.goto(review.baseURL + '/?mode=chat&tab=library')
      await page.getByRole('button', { name: 'Explore', exact: true }).click()
      await page.getByText(entry.name, { exact: true }).click()
      const dialog = page.getByRole('dialog', { name: entry.name, exact: true })
      const evidence = dialog.getByRole('region', { name: 'Validation evidence', exact: true })
      await evidence.getByText(origin, {exact:true}).waitFor()
      if (name === 'measured') { await evidence.getByText('12 test cases', { exact: true }).waitFor(); await evidence.getByText('Sep 1, 2026', { exact: true }).waitFor() }
      if (name === 'regression') await evidence.getByText(/A regression is awaiting review/).waitFor()
      await evidence.scrollIntoViewIfNeeded()
      const id = `catalog-evidence-${name}-${width}`
      await review.capture(id)
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${id}: overflow`)
      assert.deepEqual(JSON.parse(await readFile(resolve(review.out, `${id}.axe.json`), 'utf8')), [], `${id}: accessibility`)
      await dialog.getByRole('button', { name: 'Save to Library', exact: true }).scrollIntoViewIfNeeded()
      await dialog.getByRole('button', { name: 'Close', exact: true }).focus(); await page.keyboard.press('Enter')
      await dialog.waitFor({ state: 'hidden' })
      console.log(`Captured ${id}`)
    }
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('catalog-evidence-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
