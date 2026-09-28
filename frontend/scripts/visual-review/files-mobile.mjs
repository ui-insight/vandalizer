import assert from 'node:assert/strict'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT || '../artifacts/visual-review/files-mobile', baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5182' })
const { page } = review
try {
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 700 })
    await page.goto(review.baseURL + '/?mode=files')
    const checkbox = page.getByRole('checkbox', { name: 'Select Proposal narrative.pdf', exact: true })
    await checkbox.waitFor()
    await review.capture(`files-${width}`)
    await checkbox.check()
    await review.capture(`files-bulk-actions-${width}`)
    const folderName = await page.getByRole('row', { name: 'Folder: FY2027 proposals', exact: true }).locator('.file-name').boundingBox()
    assert.ok(folderName && folderName.width >= 100 && folderName.height < 60, 'Watched badge must not squeeze the folder name')
    for (const name of ['Download', 'Move', 'Delete', 'Clear selection']) {
      const box = await page.getByRole('group', { name: 'Selected files and bulk actions' }).getByRole('button', { name, exact: true }).boundingBox()
      assert.ok(box && box.x >= 0 && box.x + box.width <= width, `${name} must fit at ${width}px`)
    }
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await page.getByRole('button', { name: 'Clear selection', exact: true }).click()
    assert.equal(await checkbox.isChecked(), false)
  }
} catch (error) {
  review.errors.push(String(error))
  await review.capture('files-mobile-blocked', String(error))
  process.exitCode = 1
} finally {
  await review.flush()
  await review.browser.close()
  if (review.errors.length || review.unmatched.size) process.exitCode = 1
  console.log(JSON.stringify({ captures: review.captures.length, errors: review.errors, unmatched: [...review.unmatched] }))
}
