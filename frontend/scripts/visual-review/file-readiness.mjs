import assert from 'node:assert/strict'
import { expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { docs, workflow } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
const cases = [
  { ...docs[0], ingestion_warning_text: 'Only the first 30 pages could be read.' },
  { ...docs[1], ingest_error: 'Index service unavailable' },
  { ...docs[2], task_status: 'error' },
  { ...docs[0], id: 'doc-3', uuid: 'doc-3', title: 'Unreadable scan.pdf', extraction_low_quality: true },
  { ...docs[0], id: 'doc-4', uuid: 'doc-4', title: 'New notice.pdf', processing: true, task_status: 'ocr' },
  { ...docs[0], id: 'doc-5', uuid: 'doc-5', title: 'Rejected upload.pdf', valid: false, validation_feedback: 'The file could not be validated.' },
]
await page.route('**/api/documents/list*', r => r.fulfill({ json: { folders: [], documents: cases } }))
await page.route('**/api/files/download?*', r => r.fulfill({ contentType: 'text/plain', body: 'Synthetic partial document. The budget needs review.' }))
await page.route('**/api/workflows/workflow-1', r => r.fulfill({ json: { ...workflow, steps: [{ id: 'step-1', name: 'Review', data: {}, is_output: true, tasks: [{ id: 'task-1', name: 'Prompt', data: { prompt: 'Review the source.' } }] }] } }))
async function shot(id) { await review.capture(id); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow'); assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility'); console.log('Captured ' + id) }
try {
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: width === 320 ? 700 : 1000 }); await page.goto(review.baseURL + '/?mode=files')
    for (const doc of cases) {
      const row = page.getByRole('row', { name: 'Document: ' + doc.title, exact: true }); await expect(async () => { await row.scrollIntoViewIfNeeded() }).toPass({ timeout: 15000 }); await shot('file-readiness-' + doc.uuid + '-' + width)
    }
    for (const doc of cases.slice(0, 2)) await page.getByRole('checkbox', { name: 'Select ' + doc.title, exact: true }).check()
    await page.getByRole('button', { name: /^(?:Open )?Library(?: panel)?$/ }).click(); await page.getByRole('button', { name: 'Open Proposal readiness review', exact: true }).click()
    const notice = page.getByRole('region', { name: 'Selected document readiness', exact: true })
    await notice.locator('summary').click()
    await notice.getByText(/Only the first 30 pages/).waitFor(); await notice.getByText(/Search indexing failed/).waitFor(); await shot('file-readiness-beside-workflow-' + width)
    await notice.getByRole('button', { name: 'Inspect input: ' + docs[0].title, exact: true }).click()
    if (width < 768) await page.getByRole('button', { name: 'Files panel', exact: true }).click()
    await page.getByRole('heading', { name: docs[0].title, exact: true }).waitFor()
    if (width < 768) await page.getByRole('button', { name: 'Open tool panel', exact: true }).click()
    await page.getByRole('button', { name: 'Close workflow', exact: true }).click()
    await page.getByRole('button', { name: width < 768 ? 'Open Assistant panel' : 'Assistant', exact: true }).click()
    await notice.getByText(/Only the first 30 pages/).waitFor(); await notice.getByText(/Search indexing failed/).waitFor(); assert.equal(await notice.getByRole('button', { name: /^Inspect input:/ }).count(), 2)
    await shot('file-readiness-chat-selection-retained-' + width)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push('Six recorded readiness states in Files and persistent selected-input caveats beside workflow/chat at 320/1440. Inspection preserves both selected inputs and the open tool. Synthetic metadata; actual format/ingestion checks remain separate.')
} catch (error) { await review.capture('file-readiness-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
