import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { automation } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
let item, patches = [], fail = false, release = null, hold = false
const other = { ...automation, id: 'auto-other', name: 'Another automation' }
await page.route('**/api/automations', route => route.fulfill({ json: [item, other] }))
await page.route('**/api/automations/auto-other', route => route.fulfill({ json: other }))
await page.route('**/api/automations/auto-1', async route => {
  if (route.request().method() === 'PATCH') {
    const body = route.request().postDataJSON(); patches.push(body)
    if (hold) await new Promise(resolve => { release = resolve })
    if (fail) return route.fulfill({ status: 503, json: { detail: 'Changes could not be saved.' } })
    item = { ...item, ...body }
  }
  return route.fulfill({ json: item })
})
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
async function open(name, width) {
  if (width < 768 && await page.getByRole('button', { name: 'Automations panel', exact: true }).count()) await page.getByRole('button', { name: 'Automations panel', exact: true }).click()
  await page.getByRole('button', { name: 'Open automation: ' + name, exact: true }).click()
  await page.getByRole('textbox', { name: 'Automation description' }).waitFor()
}
try {
  for (const [width, height] of [[320, 568], [768, 700], [1440, 900]]) {
    item = { ...automation }; patches = []; fail = false; hold = false
    await page.setViewportSize({ width, height }); await page.goto(review.baseURL + '/?mode=automations')
    await open(item.name, width)
    await page.getByRole('button', { name: 'Rename automation' }).click()
    const name = page.getByRole('textbox', { name: 'Automation name', exact: true })
    await name.fill('Cancelled name'); await page.getByRole('button', { name: 'Cancel rename' }).click()
    assert.equal(patches.length, 0)
    await page.getByRole('button', { name: 'Rename automation' }).click()
    await name.fill('Renamed proposal review')
    await name.dispatchEvent('keydown', { key: 'Enter', isComposing: true })
    assert.equal(patches.length, 0)
    hold = true; await name.press('Enter')
    await page.getByText('Saving changes…', { exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: 'Save name' }).isDisabled(), true)
    await shot('automation-save-name-pending-' + width)
    hold = false; release()
    await page.getByRole('button', { name: 'Rename automation' }).waitFor()
    assert.deepEqual(patches, [{ name: 'Renamed proposal review' }])
    fail = true
    await page.getByRole('textbox', { name: 'Automation description' }).fill('Draft kept while switching tools')
    await page.getByRole('button', { name: 'Retry save' }).waitFor()
    await shot('automation-save-draft-error-' + width)
    const count = patches.length
    await open(other.name, width); await open(item.name, width)
    await page.getByRole('button', { name: 'Retry save' }).waitFor()
    assert.equal(await page.getByRole('textbox', { name: 'Automation description' }).inputValue(), 'Draft kept while switching tools')
    assert.equal(patches.length, count)
    await shot('automation-save-reopened-draft-' + width)
    fail = false; await page.getByRole('button', { name: 'Retry save' }).click()
    await page.getByText('All changes saved automatically', { exact: true }).waitFor()
    assert.equal(item.description, 'Draft kept while switching tools')
    await page.getByRole('textbox', { name: 'Automation description' }).fill('')
    await page.getByText('All changes saved automatically', { exact: true }).waitFor()
    assert.equal(item.description, '')
    await shot('automation-save-cleared-description-' + width)
    fail = true; await page.getByRole('button', { name: 'Enabled', exact: true }).click()
    await page.getByRole('button', { name: 'Retry save' }).waitFor()
    assert.equal(item.enabled, true)
    await shot('automation-save-pause-error-' + width)
    fail = false; hold = true; await page.getByRole('button', { name: 'Retry save' }).click()
    await page.getByText('Saving changes…', { exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: 'Enabled', exact: true }).isDisabled(), true)
    hold = false; release()
    await page.getByRole('button', { name: 'Disabled', exact: true }).waitFor()
    assert.equal(item.enabled, false)
    await page.getByRole('button', { name: 'Disabled', exact: true }).click()
    await page.getByRole('button', { name: 'Enabled', exact: true }).waitFor()
    assert.equal(item.enabled, true)
    await shot('automation-save-enabled-' + width)
    await page.getByRole('button', { name: 'Close automation', exact: true }).click()
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('automation-save-blocked', String(error)); throw error }
finally { if (hold && release) release(); await review.flush(); await review.browser.close() }
