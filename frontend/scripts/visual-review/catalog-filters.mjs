import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { catalog } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(10000)
const pool = Array.from({ length: 65 }, (_, i) => ({ ...catalog[0], id: `review-${i}`, item_id: `review-${i}`, source_uuid: `review-${i}`, name: `Research template ${String(i).padStart(2, '0')}`, display_name: `Research template ${String(i).padStart(2, '0')}`, kind: i % 3 === 0 ? 'knowledge_base' : i % 3 === 1 ? 'workflow' : 'search_set', quality_tier: i % 2 ? 'good' : 'excellent', quality_score: i % 2 ? 80 : 95 }))
let failItems = false, failCollections = false, failMore = false, requests = []
await page.route('**/api/verification/collections**', route => failCollections ? route.fulfill({ status: 503, json: { detail: 'Collections unavailable' } }) : route.fulfill({ json: { collections: [] } }))
await page.route('**/api/verification/verified?*', route => {
  const q = new URL(route.request().url()).searchParams, args = Object.fromEntries(q); requests.push(args)
  if (failItems || (failMore && Number(q.get('skip')) > 0)) return route.fulfill({ status: 503, json: { detail: 'Catalog unavailable' } })
  let result = pool.filter(item => (!q.get('kind') || item.kind === q.get('kind')) && (!q.get('quality_tier') || item.quality_tier === q.get('quality_tier')) && (!q.get('search') || item.name.toLowerCase().includes(q.get('search').toLowerCase())))
  if (q.get('sort') === 'name') result = [...result].sort((a,b) => a.name.localeCompare(b.name))
  const skip = Number(q.get('skip') || 0), limit = Number(q.get('limit') || 30)
  return route.fulfill({ json: { items: result.slice(skip, skip + limit), total: result.length } })
})
async function shot(id, target) {
  if (target) await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, `${id}.axe.json`), 'utf8')), [], `${id}: accessibility`)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${id}: overflow`)
  console.log(`Captured ${id}`)
}
try {
  for (const [width,height] of [[320,568],[768,600],[1440,900]]) {
    for (const surface of ['catalog','knowledge']) {
      failItems = false; failMore = false; failCollections = true; requests = []
      await page.setViewportSize({ width,height })
      await page.goto(review.baseURL + (surface === 'catalog' ? '/?mode=chat&tab=library' : '/?mode=knowledge'))
      await page.getByRole(surface === 'catalog' ? 'button' : 'tab', { name: 'Explore', exact: true }).click()
      await page.getByRole('button', { name: 'Retry collections', exact: true }).waitFor()
      await shot(`${surface}-collections-error-${width}`, page.getByRole('button', { name: 'Retry collections' }))
      failCollections = false
      await page.getByRole('button', { name: 'Retry collections' }).click()
      await page.getByRole('button', { name: 'Retry collections' }).waitFor({ state: 'hidden' })
      const search = page.getByRole(surface === 'catalog' ? 'textbox' : 'searchbox', { name: surface === 'catalog' ? 'Search catalog items' : 'Search knowledge bases', exact: true })
      const quality = page.getByRole('combobox', { name: surface === 'catalog' ? 'Filter by quality' : 'Filter by quality tier', exact: true })
      const sort = page.getByRole('combobox', { name: surface === 'catalog' ? 'Sort items' : 'Sort knowledge bases', exact: true })
      if (surface === 'catalog') await page.getByRole('button', { name: 'Workflows', exact: true }).click()
      await search.fill('template 0'); await quality.selectOption('excellent'); await sort.selectOption('name')
      await page.waitForResponse(res => { const q = new URL(res.url()).searchParams; return res.url().includes('/verification/verified?') && q.get('search') === 'template 0' && q.get('sort') === 'name' && q.get('quality_tier') === 'excellent' })
      await page.getByText(surface === 'catalog' ? 'Research template 04' : 'Research template 00', { exact: true }).waitFor()
      const last = requests.at(-1)
      assert.equal(last.kind, surface === 'catalog' ? 'workflow' : 'knowledge_base'); assert.equal(last.search, 'template 0'); assert.equal(last.quality_tier, 'excellent'); assert.equal(last.sort, 'name')
      await shot(`${surface}-combined-filters-${width}`, search)
      await search.fill('no-such-template')
      await page.getByText(surface === 'catalog' ? 'No matching items' : 'No matching knowledge bases', { exact: true }).waitFor()
      await shot(`${surface}-no-results-${width}`, page.getByRole('button', { name: 'Clear filters', exact: true }))
      await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
      await page.getByText('Research template 00', { exact: true }).waitFor()
      assert.equal(await search.inputValue(), ''); assert.equal(await quality.inputValue(), ''); assert.equal(await sort.inputValue(), '')
      await shot(`${surface}-filters-cleared-${width}`, search)
      failItems = true; await quality.selectOption('fair')
      await page.getByRole('button', { name: 'Retry', exact: true }).waitFor()
      assert.equal(await page.getByText(surface === 'catalog' ? 'No matching items' : 'No matching knowledge bases', { exact: true }).count(), 0)
      await shot(`${surface}-query-error-${width}`, page.getByRole('button', { name: 'Retry', exact: true }))
      failItems = false; await page.getByRole('button', { name: 'Retry', exact: true }).click()
      await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
      await page.getByText('Research template 00', { exact: true }).waitFor()
      if (surface === 'catalog') {
        failMore = true; await page.getByRole('button', { name: /Load more/ }).click()
        await page.getByText(/Your current results are preserved/).waitFor()
        await shot(`${surface}-pagination-error-${width}`, page.getByRole('button', { name: /Load more/ }))
        failMore = false; await page.getByRole('button', { name: /Load more/ }).click()
        await page.getByRole('button', { name: /Load more \(5 remaining\)/ }).waitFor()
        await shot(`${surface}-pagination-retried-${width}`, page.getByRole('button', { name: /Load more/ }))
      }
    }
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('catalog-filters-blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
