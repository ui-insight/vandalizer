import assert from 'node:assert/strict'
import { createReview } from './harness.mjs'

const review = await createReview({ output: process.env.REVIEW_OUTPUT || '../artifacts/visual-review/responsive', baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5180' })
const { page, state } = review
page.setDefaultTimeout(8000)
async function go(path) { await page.goto(review.baseURL + path); await page.getByRole('main').waitFor(); await page.waitForTimeout(400) }
async function capture(id) {
  await review.capture(id)
  const width = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }))
  assert.ok(width.document <= width.viewport, `${id}: ${width.document}px content exceeds ${width.viewport}px viewport`)
}
try {
  for (const width of [320, 390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: width < 600 ? 844 : 1000 })
    for (const [name, path] of [['chat', '/?mode=chat'], ['files', '/?mode=files'], ['projects', '/?mode=projects'], ['automations', '/?mode=automations'], ['knowledge', '/?mode=knowledge'], ['library', '/?mode=chat&tab=library']]) {
      await go(path)
      await capture(`${name}-${width}`)
    }
  }
  await page.setViewportSize({ width: 390, height: 700 })
  await go('/?mode=projects')
  await page.getByRole('searchbox', { name: 'Search projects' }).fill('No matching project')
  await capture('projects-no-results-mobile')
  await page.getByRole('button', { name: 'Clear search' }).click()
  await page.getByRole('button', { name: /^Community resilience proposal/ }).waitFor()
  await go('/?mode=files')
  await page.getByRole('button', { name: 'Ask assistant' }).click()
  await capture('context-assistant-mobile')
  await page.getByRole('button', { name: 'Close assistant' }).click()
  await page.getByRole('heading', { name: 'Files', exact: true }).waitFor()
  await go('/?mode=automations')
  await page.getByRole('button', { name: 'New', exact: true }).click()
  await page.getByPlaceholder('e.g. Process grant applications').fill('Mobile draft')
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await capture('automation-wizard-mobile')
  await page.keyboard.press('Escape')
  await capture('automation-discard-mobile')
  await page.getByRole('button', { name: 'Keep editing' }).click()
  assert.equal(await page.getByRole('dialog').count(), 1)
  await go('/?mode=knowledge')
  await page.getByRole('tab', { name: 'Explore', exact: true }).click()
  await capture('knowledge-catalog-mobile')
  await go('/?mode=chat&tab=library')
  await page.getByRole('button', { name: 'Explore', exact: true }).click()
  await capture('catalog-mobile')
  state.validationQueries = true
  await go('/?mode=knowledge')
  await page.getByRole('button', { name: 'Edit', exact: true }).click()
  await capture('knowledge-sources-mobile')
  await page.getByRole('tab', { name: 'Validation', exact: true }).click()
  await page.getByRole('tab', { name: 'Improve retrieval', exact: true }).click()
  await page.getByRole('button', { name: 'Validate & improve', exact: true }).click()
  await capture('validation-wizard-mobile-questions')
  for (const name of ['review', 'baseline', 'budget']) {
    await page.getByRole('dialog').getByRole('button', { name: 'Next', exact: false }).click()
    await capture(`validation-wizard-mobile-${name}`)
    if(name === 'budget'){await page.getByRole('dialog').getByRole('button',{name:/Validate & improve:/}).scrollIntoViewIfNeeded();await capture('validation-wizard-mobile-final-action')}
  }
} catch (error) {
  review.errors.push(String(error))
  await review.capture('responsive-blocked', String(error))
  process.exitCode = 1
} finally {
  await review.flush()
  await review.browser.close()
  if (review.unmatched.size || review.errors.length) process.exitCode = 1
  console.log(JSON.stringify({ captures: review.captures.length, errors: review.errors, unmatched: [...review.unmatched] }, null, 2))
}
