import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { kb, stamp } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
state.validationQueries = true
page.setDefaultTimeout(10000)
let current, failure = '', hold = false, release, readonly = false
const calls = []
const other = { ...kb, uuid: 'kb-2', title: 'Other knowledge base', sources: [], total_sources: 0, sources_ready: 0, sources_failed: 0 }
const reset = () => { current = structuredClone(kb); failure = ''; hold = false; readonly = false }
reset()
await page.route('**/api/knowledge/list/v2*', route => route.fulfill({ json: { items: [current, other], total: 2 } }))
await page.route('**/api/knowledge/kb-1', route => route.fulfill({ json: { ...current, can_manage: !readonly } }))
await page.route('**/api/knowledge/kb-2', route => route.fulfill({ json: other }))
await page.route('**/api/knowledge/kb-1/source/*', async route => {
  const req = route.request(), path = new URL(req.url()).pathname, pieces = path.split('/'), id = pieces[5], action = pieces[6] || req.method()
  const source = current.sources.find(s => s.uuid === id)
  calls.push({ path, method: req.method() })
  if (failure === action) return route.fulfill({ status: 503, json: { detail: 'Source service temporarily unavailable' } })
  if (hold && action === 'reprocess') await new Promise(resolve => { release = resolve })
  if (req.method() === 'GET') return route.fulfill({ json: { ...source, content: 'The indexed policy says the proposal is due October 15. Review this passage before relying on the answer.', document_exists: true, document_file: 'no_access', can_manage: !readonly } })
  if (req.method() === 'PATCH') Object.assign(source, req.postDataJSON())
  else if (req.method() === 'DELETE') { current.sources = current.sources.filter(s => s.uuid !== id); current.total_sources = current.sources.length; current.sources_ready = current.sources.filter(s => s.status === 'ready').length; current.sources_failed = current.sources.filter(s => s.status === 'error').length }
  else { source.status = 'pending'; source.error_message = null; current.status = 'building' }
  return route.fulfill({ json: { ...source, ok: true, status: source?.status, source_uuid: id, mode: source?.source_type === 'url' ? 'refetch' : 'reindex' } })
})
// Playwright's single-star matches only one URL segment, so register the two action routes explicitly.
await page.route('**/api/knowledge/kb-1/source/*/*', async route => {
  const req = route.request(), pieces = new URL(req.url()).pathname.split('/'), id = pieces[5], action = pieces[6]
  const source = current.sources.find(s => s.uuid === id)
  calls.push({ path: new URL(req.url()).pathname, method: req.method() })
  if (failure === action) return route.fulfill({ status: 503, json: { detail: 'Source service temporarily unavailable' } })
  if (hold && action === 'reprocess') await new Promise(resolve => { release = resolve })
  source.status = 'pending'; source.error_message = null; current.status = 'building'
  return route.fulfill({ json: { ok: true, status: 'queued', source_uuid: id, mode: source.source_type === 'url' ? 'refetch' : 'reindex' } })
})
async function open() {
  await page.goto(review.baseURL + '/?mode=knowledge')
  await page.getByRole('button', { name: 'Edit', exact: true }).first().click()
  await page.getByRole('tab', { name: /Sources \(/ }).waitFor()
}
async function shot(id, locator) {
  if (locator) await locator.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${id}: overflow`)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, `${id}.axe.json`), 'utf8')), [], `${id}: accessibility`)
  console.log(`Captured ${id}`)
}
try {
  for (const [width, height] of [[320,568],[768,600],[1440,900]]) {
    reset(); await page.setViewportSize({ width, height }); await open()
    await shot(`source-readable-status-${width}`, page.getByRole('button', { name: 'Inspect source: Proposal narrative.pdf' }))
    failure = 'refresh'; await page.getByRole('button', { name: 'Refresh source', exact: true }).first().click()
    await page.getByRole('alert').filter({ hasText: 'Could not refresh' }).waitFor()
    await shot(`source-refresh-error-${width}`, page.getByRole('alert').filter({ hasText: 'Could not refresh' }))
    failure = ''; await page.getByRole('button', { name: 'Refresh source', exact: true }).first().click()
    await page.getByText('Web page · Queued', { exact: true }).waitFor()
    await shot(`source-refresh-queued-${width}`, page.getByText('Web page · Queued', { exact: true }))
    current.status = 'ready'; current.sources[1].status = 'ready'
    current.sources[1].currency = { status: 'retained_previous', last_refresh_outcome: 'retrieval_failed', last_refresh_error: 'Remote page unavailable', last_refresh_attempted_at: stamp, content_retrieved_at: '2026-06-01T12:00:00Z' }
    await page.getByText(/Refresh failed.*serving text from/).waitFor()
    await shot(`source-retained-previous-${width}`, page.getByText(/Refresh failed.*serving text from/))
    await page.getByRole('button', { name: 'Try again', exact: true }).click()
    await page.getByRole('button', { name: 'Try again', exact: true }).waitFor({ state: 'hidden' })
    current.sources[2].status = 'ready'; current.sources[2].chunk_count = 18; current.status = 'ready'
    await page.getByText('18 chunks · Freshness not recorded', { exact: true }).waitFor()
    await shot(`source-retry-complete-${width}`, page.getByText('18 chunks · Freshness not recorded', { exact: true }))
    await page.getByRole('button', { name: 'Rename source', exact: true }).first().click()
    await page.getByRole('textbox', { name: 'Source name', exact: true }).fill('Reviewed proposal narrative')
    failure = 'PATCH'; await page.getByRole('button', { name: 'Save name', exact: true }).click()
    await page.getByRole('alert').filter({ hasText: 'Your draft is preserved' }).waitFor()
    await shot(`source-rename-error-${width}`, page.getByRole('textbox', { name: 'Source name', exact: true }))
    failure = ''; await page.getByRole('button', { name: 'Save name', exact: true }).click()
    await page.getByRole('button', { name: 'Inspect source: Reviewed proposal narrative', exact: true }).waitFor()
    failure = 'GET'; await page.getByRole('button', { name: 'Inspect source: Reviewed proposal narrative', exact: true }).click()
    await page.getByRole('button', { name: 'Retry source', exact: true }).waitFor()
    await shot(`source-inspector-error-${width}`)
    failure = ''; await page.getByRole('button', { name: 'Retry source', exact: true }).click()
    await page.getByText(/The indexed policy says/).waitFor()
    await shot(`source-inspector-recovered-${width}`)
    await page.getByRole('textbox', { name: 'Source', exact: true }).fill('Reviewed reference')
    failure = 'PATCH'; await page.getByRole('button', { name: 'Save source', exact: true }).click()
    await page.getByRole('alert').filter({ hasText: 'Your source text is preserved' }).waitFor()
    assert.equal(await page.getByText(/The indexed policy says/).isVisible(), true)
    await shot(`source-provenance-error-${width}`)
    await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click()
    failure = 'DELETE'; await page.getByRole('button', { name: 'Remove source', exact: true }).last().click()
    await page.getByRole('alert').filter({ hasText: 'Could not remove' }).waitFor()
    await shot(`source-remove-error-${width}`, page.getByRole('alert').filter({ hasText: 'Could not remove' }))
    failure = ''; await page.getByRole('button', { name: 'Remove source', exact: true }).last().click()
    await page.getByRole('tab', { name: 'Sources (2)', exact: true }).waitFor()
    readonly = true; await open()
    assert.equal(await page.getByRole('button', { name: 'Refresh source', exact: true }).count(), 0)
    await page.getByRole('button', { name: 'Inspect source: Reviewed proposal narrative', exact: true }).click()
    await page.getByText(/The indexed policy says/).waitFor()
    assert.equal(await page.getByRole('textbox', { name: 'Source', exact: true }).getAttribute('readonly'), '')
    await shot(`source-inspector-viewer-${width}`)
  }
  reset(); await page.setViewportSize({ width: 320, height: 568 }); await open()
  hold = true
  const before = calls.length
  await page.getByRole('button', { name: 'Reprocess source', exact: true }).click()
  assert.equal(await page.getByRole('button', { name: 'Reprocess source', exact: true }).isDisabled(), true)
  await shot('source-reprocess-submitting-320', page.getByText('Document · Submitting change…', { exact: true }))
  await page.getByRole('button', { name: 'Back to knowledge bases', exact: true }).click()
  await page.getByRole('button', { name: 'Edit', exact: true }).last().click()
  await page.getByText('Other knowledge base', { exact: true }).waitFor()
  hold = false; release()
  await page.waitForTimeout(1000)
  assert.equal(await page.getByText('Other knowledge base', { exact: true }).isVisible(), true)
  assert.equal(calls.length, before + 1)
  await shot('source-late-response-other-kb-320')
  review.observations.push('Source status/identity/freshness, refresh failure/retry/retained text, failed-source recovery, rename draft retry, inspector load retry and preserved text on provenance error, remove error/success, viewer permissions and late response after switching KB. 320/768/1440px synthetic APIs; no actual ingestion/refresh execution.')
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('source-recovery-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
