import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { kb } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
let fail = true
const rows = Array.from({ length: 205 }, (_, i) => ({ ...kb, uuid: 'kb-' + i, title: 'Research knowledge base ' + i }))
await page.route('**/api/projects/project-1/pins', route => fail ? route.fulfill({ status: 503, json: { detail: 'Pins unavailable.' } }) : route.fulfill({ json: [{ pin_type: 'knowledge_base', target_id: 'kb-204' }] }))
await page.route('**/api/knowledge/list/v2*', route => {
  const q = new URL(route.request().url()).searchParams, skip = Number(q.get('skip') || 0), limit = Number(q.get('limit') || 50)
  return route.fulfill({ json: { items: rows.slice(skip, skip + limit), total: rows.length } })
})
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
try {
  for (const [width, height] of [[320,568],[768,700],[1440,900]]) {
    fail = true; await page.setViewportSize({ width, height }); await page.goto(review.baseURL + '/?mode=knowledge&project=project-1')
    await page.getByRole('button', { name: 'Retry project knowledge bases', exact: true }).waitFor()
    await shot('knowledge-project-pins-error-' + width)
    fail = false; await page.getByRole('button', { name: 'Retry project knowledge bases', exact: true }).click()
    await page.getByRole('button', { name: 'Research knowledge base 204', exact: true }).waitFor()
    assert.equal(await page.getByRole('article').count(), 1)
    await shot('knowledge-project-later-page-' + width)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push('Project pin failure/retry, and exactly the pinned KB from the second server page at 320/768/1440px. Synthetic APIs, no live permission check.')
} catch (error) { await review.capture('knowledge-project-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
