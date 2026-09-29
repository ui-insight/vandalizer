import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { validationResult } from './fixtures.mjs'

const shortScreens = process.env.REVIEW_SHORT === '1'
const viewports = shortScreens ? [[320,480],[768,500],[1440,600]] : [[320,568],[768,600],[1440,900]]
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
state.validationQueries = true
page.setDefaultTimeout(10000)
let failHistory = false, failExport = false, empty = false
const exports = [], starts = []
const history = Array.from({ length: 30 }, (_, i) => ({
  uuid: `review-run-${i}`, score: i === 28 ? null : 66 + (i % 10),
  created_at: `2026-09-${String(30-i).padStart(2, '0')}T12:00:00Z`, source: i === 1 ? 'smoke_test' : i === 2 ? 'optimizer_apply' : 'manual',
  judge_model: i === 0 ? 'Current evaluation model with a long descriptive name' : 'Previous evaluation model',
  model: 'Answer model used for this saved check', mode: i === 1 ? 'judge' : 'judge+baseline', num_queries_judged: 3,
  question_set: { fingerprint: i === 0 ? 'changed-evaluation-question-set-20260930' : 'original-evaluation-question-set-20260901', count: 3, category_counts: { factual: 3 } },
  query_selection: i === 1 ? { selected: 3, total: 10 } : null,
  result_snapshot: i === 2 || i === 28 ? null : { ...validationResult, judge_model: i === 0 ? 'Current evaluation model' : 'Previous evaluation model', score: 66 + (i % 10), score_breakdown: { ...validationResult.score_breakdown, final_score: 66 + (i % 10) }, question_set: { fingerprint: `saved-set-${i}`, count: 3, category_counts: { factual: 3 } } },
}))
await page.route('**/api/knowledge/kb-1/quality', route => failHistory
  ? route.fulfill({ status: 503, json: { detail: 'History temporarily unavailable' } })
  : route.fulfill({ json: { history: empty ? [] : history, contract: {} } }))
await page.route('**/api/knowledge/kb-1/validation-runs/*/export?*', route => {
  const url = new URL(route.request().url()); exports.push(url.pathname + url.search)
  return failExport ? route.fulfill({ status: 503, json: { detail: 'Export temporarily unavailable' } })
    : route.fulfill({ status: 200, body: 'synthetic review export', headers: { 'content-type': 'application/octet-stream', 'content-disposition': 'attachment; filename="review-export.txt"' } })
})
await page.route('**/api/knowledge/kb-1/validate', route => { starts.push(route.request().postData()); return route.fulfill({ status: 500, json: { detail: 'Unexpected validation request' } }) })
async function shot(id) {
  if (shortScreens) id += '-short'
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${id}: overflow`)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, `${id}.axe.json`), 'utf8')), [], `${id}: accessibility findings`)
  console.log(`Captured ${id}`)
}
async function openHistory() {
  await page.goto(review.baseURL + '/?mode=knowledge')
  await page.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByRole('tab', { name: 'Validation', exact: true }).click()
  await page.getByRole('tab', { name: 'History', exact: true }).click()
}
try {
  for (const [width, height] of viewports) {
    await page.setViewportSize({ width, height })
    await openHistory()
    await page.getByText('Last 30 runs', { exact: true }).waitFor()
    assert.equal(await page.getByRole('article', { name: /Validation run/ }).count(), 30)
    await shot(`validation-history-comparison-${width}`)
    await page.getByRole('article', { name: /· review-run-0$/ }).scrollIntoViewIfNeeded()
    await shot(`validation-history-run-card-${width}`)
    const oldest = page.getByRole('article', { name: /· review-run-29$/ })
    await oldest.getByRole('button', { name: 'Export run results' }).click()
    await shot(`validation-history-oldest-export-${width}`)
    failExport = true
    await oldest.getByRole('button', { name: 'CSV', exact: true }).click()
    await oldest.getByRole('alert').waitFor()
    await shot(`validation-history-export-error-${width}`)
    failExport = false
    const download = page.waitForEvent('download')
    await oldest.getByRole('button', { name: 'JSON', exact: true }).click()
    await download
    assert.equal(exports.at(-1), '/api/knowledge/kb-1/validation-runs/review-run-29/export?format=json')
    await oldest.getByRole('button', { name: 'Open results' }).focus()
    await page.keyboard.press('Enter')
    await page.getByText(/Saved run .*review-run-29/).waitFor()
    await page.getByText(/Saved run .*review-run-29/).scrollIntoViewIfNeeded()
    const modeBox = await page.getByRole('combobox', { name: 'Mode:' }).boundingBox()
    assert.ok(modeBox && modeBox.x + modeBox.width <= width, 'Scoring mode must fit narrow screens')
    await shot(`validation-history-opened-result-${width}`)
    assert.equal(await page.getByText(/saved-set-29/).count(), 1)
    for (const [label, format] of [['CSV','csv'], ['Excel','xlsx'], ['JSON','json']]) {
      const dl = page.waitForEvent('download')
      await page.getByRole('button', { name: label, exact: true }).click(); await dl
      assert.equal(exports.at(-1), `/api/knowledge/kb-1/validation-runs/review-run-29/export?format=${format}`)
    }
    assert.equal(starts.length, 0, 'Reopening/exporting a saved run must never launch a new validation')
  }
  await page.setViewportSize({ width: 320, height: shortScreens ? 480 : 568 })
  failHistory = true
  await openHistory()
  await page.getByRole('button', { name: 'Retry history' }).waitFor()
  await shot('validation-history-load-error-320')
  failHistory = false
  await page.getByRole('button', { name: 'Retry history' }).click()
  await page.getByText('Last 30 runs', { exact: true }).waitFor()
  await shot('validation-history-load-recovered-320')
  empty = true
  await openHistory()
  await page.getByText('No quality history yet for this KB', { exact: true }).waitFor()
  await shot('validation-history-empty-320')
  review.observations.push('30 saved runs remain available at 320/768/1440px. Oldest saved run opened by keyboard and exported as CSV, Excel and JSON using its exact UUID; no validation POST. History and export 503 errors recover explicitly. All responses synthetic; delayed/failed task lifecycle remains unverified.')
  assert.deepEqual([...review.unmatched], [])
  assert.deepEqual(review.errors, [])
} finally { await review.flush(); await review.browser.close() }
