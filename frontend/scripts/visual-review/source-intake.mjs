import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { kb, docs, stamp } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(10000)
let current, fail = '', requests = []
await page.route('**/api/knowledge/kb-1', route => route.fulfill({ json: current }))
await page.route('**/api/documents/search?*', route => fail === 'search' ? route.fulfill({ status: 503, json: { detail: 'Document search unavailable' } }) : route.fulfill({ json: { items: docs, total: docs.length } }))
await page.route('**/api/knowledge/kb-1/add_*', route => {
  const kind = route.request().url().split('/').at(-1), body = route.request().postDataJSON()
  requests.push({ kind, body })
  if (fail === kind) return route.fulfill({ status: 503, json: { detail: 'Source registration unavailable' } })
  if (kind === 'add_documents') {
    current.sources.push(...body.document_uuids.map(id => ({ uuid: `source-${id}`, source_type: 'document', document_uuid: id, document_title: docs.find(d => d.uuid === id).title, status: 'pending', chunk_count: 0, created_at: stamp })))
    current.status = 'building'; current.total_sources = current.sources.length
    return route.fulfill({ json: { ok: true, added: body.document_uuids.length } })
  }
  if (kind === 'add_urls') {
    current.sources.push({ uuid: 'source-new-url', source_type: 'url', url: 'https://example.org/new', status: 'pending', chunk_count: 0, created_at: stamp })
    current.status = 'building'; current.total_sources = current.sources.length
    return route.fulfill({ json: { ok: true, added: 1, skipped: 1, skipped_urls: ['https://example.org/policies'] } })
  }
  return route.fulfill({ json: { ok: true, added: 0 } })
})
async function shot(id, locator) {
  if (locator) await locator.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${id}: overflow`)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, `${id}.axe.json`), 'utf8')), [], `${id}: accessibility`)
  console.log(`Captured ${id}`)
}
try {
  for (const [width, height] of [[320,568],[768,600],[1440,900]]) {
    current = structuredClone(kb); fail = ''; requests = []
    await page.setViewportSize({ width, height })
    await page.goto(review.baseURL + '/?mode=knowledge')
    await page.getByRole('button', { name: 'Edit', exact: true }).click()
    fail = 'search'; await page.getByRole('button', { name: 'Add Documents', exact: true }).click()
    await page.getByRole('button', { name: 'Retry search', exact: true }).waitFor()
    await shot(`source-intake-search-error-${width}`, page.getByRole('button', { name: 'Retry search', exact: true }))
    fail = ''; await page.getByRole('button', { name: 'Retry search', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'Add Documents', exact: true })
    await dialog.getByRole('button', { name: /Budget justification.docx/ }).click()
    await dialog.getByRole('button', { name: /Award terms/ }).click()
    fail = 'add_documents'; await dialog.getByRole('button', { name: 'Add (2)', exact: true }).click()
    await dialog.getByRole('alert').filter({ hasText: 'Your selection is preserved' }).waitFor()
    await shot(`source-intake-document-error-${width}`, dialog.getByRole('button', { name: 'Add (2)', exact: true }))
    fail = ''; await dialog.getByRole('button', { name: 'Add (2)', exact: true }).click()
    await dialog.waitFor({ state: 'hidden' })
    assert.deepEqual(requests[0].body, requests[1].body)
    await page.getByRole('tab', { name: 'Sources (5)', exact: true }).waitFor()
    await shot(`source-intake-documents-queued-${width}`, page.getByRole('button', { name: 'Inspect source: Budget justification.docx', exact: true }))
    current.sources.at(-2).status = 'ready'; current.sources.at(-2).chunk_count = 12
    current.sources.at(-1).status = 'error'; current.sources.at(-1).error_message = 'This document could not be read. Try processing it again.'
    current.status = 'ready'; current.sources_ready = 3; current.sources_failed = 2
    await page.getByText('This document could not be read. Try processing it again.', { exact: false }).waitFor()
    await shot(`source-intake-mixed-processing-${width}`, page.getByRole('button', { name: 'Inspect source: Award terms – draft.pdf', exact: true }))
    await page.getByRole('button', { name: 'Add URLs', exact: true }).click()
    const urls = page.getByRole('dialog', { name: 'Add URLs', exact: true })
    await urls.getByRole('textbox', { name: 'URLs to add, one per line' }).fill('https://example.org/policies\nhttps://example.org/new')
    await urls.getByRole('checkbox', { name: 'Enable crawling' }).check()
    await urls.getByRole('spinbutton', { name: 'Max pages' }).fill('7')
    await urls.getByRole('textbox', { name: 'Allowed domains (optional)' }).fill('example.org')
    fail = 'add_urls'; await urls.getByRole('button', { name: 'Add URLs', exact: true }).click()
    await urls.getByRole('alert').waitFor()
    await shot(`source-intake-url-error-${width}`, urls.getByRole('button', { name: 'Add URLs', exact: true }))
    fail = ''; await urls.getByRole('button', { name: 'Add URLs', exact: true }).click()
    await urls.waitFor({ state: 'hidden' })
    assert.deepEqual(requests[2].body, requests[3].body)
    assert.equal(requests[3].body.max_crawl_pages, 7)
    await page.getByText(/Queued 1 URL for retrieval and crawling. 1 already in this KB/).waitFor()
    await shot(`source-intake-url-mixed-result-${width}`)
    current.sources.at(-1).status = 'error'; current.sources.at(-1).error_message = 'Remote page unavailable.'; current.status = 'ready'
    await page.getByText('Remote page unavailable.', { exact: false }).waitFor()
    await shot(`source-intake-url-unavailable-${width}`, page.getByRole('button', { name: 'Inspect source: https://example.org/new', exact: true }))
    await page.getByRole('button', { name: 'Add Documents', exact: true }).click()
    await dialog.getByRole('combobox', { name: 'Filter by folder' }).selectOption('folder-1')
    await dialog.getByRole('checkbox', { name: 'Include subfolders' }).uncheck()
    fail = 'add_folder'; await dialog.getByRole('button', { name: 'Add entire folder', exact: true }).click()
    await dialog.getByRole('alert').filter({ hasText: 'Your selection is preserved' }).waitFor()
    await shot(`source-intake-folder-error-${width}`, dialog.getByRole('button', { name: 'Add entire folder', exact: true }))
    fail = ''; await dialog.getByRole('button', { name: 'Add entire folder', exact: true }).click()
    await dialog.waitFor({ state: 'hidden' })
    assert.deepEqual(requests[4].body, requests[5].body)
    assert.equal(requests[5].body.include_subfolders, false)
    await page.getByText('No new documents found in that folder', { exact: true }).waitFor()
  }
  review.observations.push('Document search and source-registration failures retain query/selection/URL/crawl/folder settings. Retries preserve request payloads. Queued, mixed-ready/failed documents, new/skipped URLs and unavailable web sources have distinct outcomes. 320/768/1440px synthetic worker outcomes only.')
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('source-intake-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
