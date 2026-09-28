import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { automation } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
let listError = true, pinsError = false, empty = false
const autos = [automation, { ...automation, id: 'auto-api', name: 'Incoming awards', description: 'Proposal intake', trigger_type: 'api', trigger_config: {} }, { ...automation, id: 'auto-schedule', name: 'Weekly proposal', trigger_type: 'schedule', trigger_config: {} }, { ...automation, id: 'auto-m365', name: 'Mailbox intake', trigger_type: 'm365_intake', trigger_config: {} }]
await page.route('**/api/automations', route => listError ? route.fulfill({ status: 503, json: { detail: 'Automation list temporarily unavailable.' } }) : route.fulfill({ json: empty ? [] : autos }))
await page.route('**/api/projects/project-1/pins', route => pinsError ? route.fulfill({ status: 503, json: { detail: 'Project pins temporarily unavailable.' } }) : route.fulfill({ json: [{ pin_type: 'automation', target_id: 'auto-api' }, { pin_type: 'automation', target_id: 'auto-schedule' }] }))
await page.route('**/api/automations/auto-api', route => route.fulfill({ json: autos[1] }))
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
try {
  for (const [width, height] of [[320, 568], [768, 700], [1440, 900]]) {
    listError = true; pinsError = false; empty = false
    await page.setViewportSize({ width, height }); await page.goto(review.baseURL + '/?mode=automations')
    await page.getByRole('button', { name: 'Retry automations', exact: true }).waitFor()
    await shot('automation-list-error-' + width)
    listError = false; await page.getByRole('button', { name: 'Retry automations', exact: true }).click()
    await page.getByRole('button', { name: 'All: 4 automations', exact: true }).waitFor()
    const search = page.getByRole('textbox', { name: 'Filter automations', exact: true })
    await search.fill(' PROPOSAL '); await page.getByRole('button', { name: 'API: 1 automations', exact: true }).click()
    await page.getByText('1 of 4 automations', { exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: 'Open automation: Incoming awards', exact: true }).count(), 1)
    await shot('automation-filter-combined-' + width)
    await search.fill('absent'); await page.getByText('No matching automations', { exact: true }).waitFor()
    await shot('automation-filter-empty-' + width)
    await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
    assert.equal(await search.inputValue(), '')
    await page.getByRole('button', { name: 'M365: 1 automations', exact: true }).click()
    await page.getByRole('button', { name: 'Open automation: Mailbox intake', exact: true }).waitFor()
    await shot('automation-filter-m365-' + width)
    await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
    await search.fill('awards'); await page.getByRole('button', { name: 'Open automation: Incoming awards', exact: true }).click()
    await page.getByRole('button', { name: 'Close automation', exact: true }).waitFor()
    listError = true; await page.getByRole('button', { name: 'Close automation', exact: true }).click()
    if (width < 768) await page.getByRole('button', { name: 'Automations panel', exact: true }).click()
    await page.getByRole('button', { name: 'Retry automations', exact: true }).waitFor()
    assert.equal(await search.inputValue(), 'awards')
    assert.equal(await page.getByRole('button', { name: 'Open automation: Incoming awards', exact: true }).count(), 1)
    await shot('automation-list-refresh-error-' + width)
    await page.getByRole('button', { name: 'Open automation: Incoming awards', exact: true }).scrollIntoViewIfNeeded()
    await shot('automation-list-retained-row-' + width)
    listError = false; await page.getByRole('button', { name: 'Retry automations', exact: true }).click()
    await page.getByRole('button', { name: 'All: 4 automations', exact: true }).waitFor()
    // A project pin lookup failure must not be presented as an empty project.
    pinsError = true; await page.goto(review.baseURL + '/?mode=automations&project=project-1')
    await page.getByRole('button', { name: 'Retry automations', exact: true }).waitFor()
    await shot('automation-project-pins-error-' + width)
    pinsError = false; await page.getByRole('button', { name: 'Retry automations', exact: true }).click()
    await page.getByRole('button', { name: 'All: 2 automations', exact: true }).waitFor()
    await page.getByRole('button', { name: 'Folder Watch: 0 automations', exact: true }).click()
    await page.getByText('No matching automations', { exact: true }).waitFor()
    await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
    assert.equal(await page.getByRole('button', { name: 'All: 2 automations', exact: true }).count(), 1)
    await shot('automation-project-filtered-' + width)
    await page.getByRole('button', { name: 'Show all', exact: true }).click()
    await page.getByRole('button', { name: 'All: 4 automations', exact: true }).waitFor()
    empty = true; await page.goto(review.baseURL + '/?mode=automations')
    await page.getByRole('button', { name: 'New', exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: 'Retry automations', exact: true }).count(), 0)
    await shot('automation-list-empty-' + width)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('automation-filters-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
