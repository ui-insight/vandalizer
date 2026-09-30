import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { items as baseItems, workflow } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
const items = baseItems.map(item => ({ ...item, name: item.name + ' for international research funding requirements and supporting evidence' }))
await page.route('**/api/library/library-1/items*', route => route.fulfill({ json: items }))
let workflowError = true, extractionError = true, promptError = true
await page.route('**/api/workflows/workflow-1', route => workflowError ? route.fulfill({ status: 503, json: { detail: 'Workflow temporarily unavailable.' } }) : route.fulfill({ json: workflow }))
await page.route('**/api/library/items/*/touch', route => route.fulfill({ json: { ok: true } }))
await page.route('**/api/extractions/test-cases?*', route => route.fulfill({ json: [] }))
await page.route('**/api/extractions/search-sets/item-1', route => extractionError ? route.fulfill({ status: 404, json: { detail: 'Extraction is unavailable or no longer shared with you.' } }) : route.fulfill({ json: { id: 'item-1', uuid: 'item-1', title: items[1].name, set_type: 'extraction', user_id: 'reviewer', extraction_config: {}, created_at: '', updated_at: '' } }))
await page.route('**/api/extractions/search-sets/item-1/**', route => {
  const path = new URL(route.request().url()).pathname
  return route.fulfill({ json: path.endsWith('/items') || path.endsWith('/test-cases') ? [] : path.endsWith('/history') ? { runs: [] } : path.endsWith('/quality-sparkline') ? { scores: [] } : {} })
})
await page.route('**/api/extractions/search-sets/item-2/items', route => promptError ? route.fulfill({ status: 503, json: { detail: 'Prompt content temporarily unavailable.' } }) : route.fulfill({ json: [{ id: 'prompt-content', searchphrase: 'Review the source and summarize its requirements.\n\n'.repeat(16) }] }))
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
async function chooseKind(value, label) {
  const select = page.getByRole('combobox', { name: 'Filter library by type' })
  if (await select.isVisible()) await select.selectOption(value)
  else await page.getByRole('button', { name: new RegExp('^' + label + '\\b') }).click()
}
try {
  for (const [width, height] of [[320, 568], [768, 700], [1440, 900]]) {
    workflowError = true; extractionError = true; promptError = true
    await page.setViewportSize({ width, height }); await page.goto(review.baseURL + '/?mode=files')
    if (width < 768) await page.getByRole('button', { name: 'Open Library panel', exact: true }).click()
    else await page.getByRole('button', { name:/^(?:Open )?Library(?: panel)?$/ }).click()
    await page.getByRole('textbox', { name: 'Search library' }).waitFor()
    await chooseKind('workflow', 'Workflows')
    assert.equal(await page.locator('.library-item-row').count(), 1)
    await page.getByRole('button', { name: 'Open ' + items[0].name, exact: true }).click()
    await page.getByRole('button', { name: 'Retry workflow' }).waitFor(); await shot('library-workflow-unavailable-' + width)
    workflowError = false; await page.getByRole('button', { name: 'Retry workflow' }).click()
    await page.getByRole('button', { name: 'Close workflow', exact: true }).waitFor(); await shot('library-workflow-recovered-' + width)
    await page.getByRole('button', { name: 'Close workflow', exact: true }).click()
    await chooseKind('extraction', 'Extractions')
    await page.getByRole('button', { name: 'Open ' + items[1].name, exact: true }).click()
    await page.getByRole('button', { name: 'Retry extraction' }).waitFor(); await shot('library-extraction-unavailable-' + width)
    extractionError = false; await page.getByRole('button', { name: 'Retry extraction' }).click()
    await page.getByRole('button', { name: 'Close extraction', exact: true }).waitFor(); await shot('library-extraction-recovered-' + width)
    await page.getByRole('button', { name: 'Close extraction', exact: true }).click()
    await chooseKind('prompt', 'Prompts')
    const prompt = page.getByRole('button', { name: 'Open ' + items[2].name, exact: true })
    await prompt.focus(); await prompt.press('Enter')
    const dialog = page.getByRole('dialog', { name: 'Preview ' + items[2].name, exact: true })
    await dialog.getByRole('button', { name: 'Retry item content' }).waitFor()
    assert.equal(await dialog.getByRole('button', { name: 'Use in Assistant' }).isDisabled(), true)
    await shot('library-prompt-content-error-' + width)
    promptError = false; await dialog.getByRole('button', { name: 'Retry item content' }).click()
    await dialog.getByText(/Review the source and summarize/).waitFor()
    await dialog.getByRole('button', { name: 'Use in Assistant' }).scrollIntoViewIfNeeded()
    await shot('library-prompt-long-content-' + width)
    await dialog.getByRole('button', { name: 'Close', exact: true }).focus()
    await page.keyboard.press('Tab')
    assert.equal(await dialog.evaluate(element => element.contains(document.activeElement)), true)
    await page.keyboard.press('Escape'); await dialog.waitFor({ state: 'detached' })
    assert.equal(await prompt.evaluate(element => element === document.activeElement), true)
    await chooseKind('all', 'All types')
    assert.equal(await page.locator('.library-item-row').count(), 3)
    await shot('library-mixed-types-return-' + width)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('library-opening-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
