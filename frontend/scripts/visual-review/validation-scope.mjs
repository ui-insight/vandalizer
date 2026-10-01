import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { kb } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
state.validationQueries = true
page.setDefaultTimeout(30000)
const other = { ...kb, uuid: 'kb-2', title: 'Other knowledge base' }
const task = { task_id: 'original-kb-task', status: 'running', message: 'Checking original KB answers…', options: { mode: 'judge', query_uuids: ['query-1'] } }
let posts = 0
await page.route('**/api/knowledge/list/v2*', route => route.fulfill({ json: { items: [kb, other], total: 2 } }))
await page.route('**/api/knowledge/kb-2', route => route.fulfill({ json: other }))
await page.route('**/api/knowledge/*/validation-tasks/*', route => {
  const url = route.request().url()
  if (url.includes('/kb-2/')) { assert.ok(url.endsWith('/active')); return route.fulfill({ json: { task: null } }) }
  return route.fulfill({ json: url.endsWith('/active') ? { task } : task })
})
await page.route('**/api/knowledge/*/validate', route => { posts++; return route.fulfill({ status: 400, json: { detail: 'No new validation expected' } }) })
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${id}: overflow`)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, `${id}.axe.json`), 'utf8')), [], `${id}: accessibility`)
  console.log(`Captured ${id}`)
}
try {
  for (const [width, height] of [[320,568],[768,600],[1440,900]]) {
    await page.setViewportSize({ width, height })
    await page.goto(review.baseURL + '/?mode=knowledge')
    await page.getByRole('button', { name: kb.title, exact: true }).click()
    await page.getByRole('tab', { name: 'Validation', exact: true }).click()
    await page.getByRole('tab', { name: 'Check answer quality', exact: true }).click()
    await page.getByText(task.message, { exact: true }).waitFor()
    await page.getByRole('button', { name: 'Back to knowledge bases' }).click()
    await page.getByRole('button', { name: other.title, exact: true }).click()
    await page.getByRole('tab', { name: 'Validation', exact: true }).click()
    await page.getByRole('tab', { name: 'Check answer quality', exact: true }).click()
    await page.getByRole('button', { name: 'Run 3 questions', exact: true }).waitFor()
    assert.equal(await page.getByText(task.message, { exact: true }).count(), 0)
    await shot(`validation-other-kb-isolated-${width}`)
    await page.getByRole('button', { name: 'Back to knowledge bases' }).click()
    await page.getByRole('button', { name: kb.title, exact: true }).click()
    await page.getByRole('tab', { name: 'Validation', exact: true }).click()
    await page.getByRole('tab', { name: 'Check answer quality', exact: true }).click()
    await page.getByText(task.message, { exact: true }).waitFor()
    await page.getByText(/1 selected questions/).waitFor()
    assert.equal(await page.getByRole('button', { name: 'Running…', exact: true }).isDisabled(), true)
    await shot(`validation-original-kb-resumed-${width}`)
  }
  assert.equal(posts, 0)
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push('Switching KBs isolates validation status; returning restores the original task and exact subset with no POST. 320/768/1440px, synthetic server state only.')
} catch (error) { await review.capture('validation-scope-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
