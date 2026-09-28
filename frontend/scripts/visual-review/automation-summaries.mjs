import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { automation } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
let folderError = false, empty = false
const input = 'Proposals / Incoming applications and supporting evidence'
const output = 'Proposals / Completed reviews and budget recommendations'
const items = [
  { ...automation, name: 'Review incoming proposals and supporting evidence for the annual awards', output_config: { storage: { enabled: true, destination_folder: 'folder-output', format: 'pdf' }, notifications: [{}], webhooks: [{ url: 'https://example.invalid/private-token' }] } },
  { ...automation, id: 'auto-api', name: 'Extract award fields from API submissions', trigger_type: 'api', action_type: 'extraction', action_name: 'Award details and eligibility requirements', output_config: {} },
  { ...automation, id: 'auto-schedule', name: 'Weekly review of newly received documents', trigger_type: 'schedule', trigger_config: { source: 'documents', document_uuids: ['doc-0', 'doc-1'], frequency: 'weekly', weekday: 0, time: '09:00', timezone: 'America/Los_Angeles', only_new: true }, output_config: { onedrive: { enabled: true }, chains: [{}] } },
  { ...automation, id: 'auto-m365', name: 'Review Microsoft 365 intake', trigger_type: 'm365_intake', action_type: 'task', output_config: {} },
]
await page.route('**/api/automations', route => route.fulfill({ json: empty ? [] : items }))
for (const item of items) await page.route('**/api/automations/' + item.id, route => route.fulfill({ json: item }))
await page.route('**/api/folders/all', route => folderError ? route.fulfill({ status: 503, json: { detail: 'Folder names temporarily unavailable.' } }) : route.fulfill({ json: [{ uuid: 'folder-1', path: input }, { uuid: 'folder-output', path: output }] }))
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
try {
  for (const [width, height] of [[320, 568], [768, 700], [1440, 900]]) {
    empty = false; folderError = false; await page.setViewportSize({ width, height }); await page.goto(review.baseURL + '/?mode=automations')
    await page.getByRole('button', { name: 'Open automation: ' + items[0].name, exact: true }).waitFor()
    await page.getByText('PDF → ' + output + ' · Notifications configured · 1 webhook', { exact: true }).waitFor()
    await shot('automation-summary-folder-' + width)
    await page.getByRole('button', { name: 'API: 1 automations', exact: true }).click()
    await page.getByText('Documents or text provided by the caller', { exact: true }).waitFor(); await shot('automation-summary-api-' + width)
    await page.getByRole('button', { name: 'Schedule: 1 automations', exact: true }).click()
    await page.getByText('2 selected documents · new files only', { exact: true }).waitFor(); await shot('automation-summary-schedule-' + width)
    await page.getByRole('button', { name: 'M365: 1 automations', exact: true }).click()
    await page.getByText('Files from the configured Microsoft 365 source', { exact: true }).waitFor(); await shot('automation-summary-m365-' + width)
    await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
    await page.getByRole('button', { name: 'Open automation: ' + items[0].name, exact: true }).click()
    const editor = page.getByRole('region', { name: 'Tools and assistant', exact: true })
    await editor.getByText('PDF → ' + output + ' · Notifications configured · 1 webhook', { exact: true }).scrollIntoViewIfNeeded()
    await shot('automation-summary-editor-' + width)
    await page.getByRole('button', { name: 'Close automation', exact: true }).click()
    if (width < 768) await page.getByRole('button', { name: 'Automations panel', exact: true }).click()
    folderError = true; await page.reload()
    await page.getByRole('button', { name: 'Retry folder names', exact: true }).waitFor(); await shot('automation-summary-folder-error-' + width)
    folderError = false; await page.getByRole('button', { name: 'Retry folder names', exact: true }).click()
    await page.getByText(input + ' · pdf, docx', { exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: 'Retry folder names', exact: true }).count(), 0)
    empty = true; await page.reload()
    await page.getByRole('heading', { name: 'No automations yet', exact: true }).waitFor(); await shot('automation-summary-empty-' + width)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('automation-summary-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
