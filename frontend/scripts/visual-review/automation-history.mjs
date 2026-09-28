import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { automation } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
let failList = true, failPage = false, failDetail = false, complete = false, empty = false, viewer = false, posts = 0, pageCursors = [], detailIds = []
const rows = Array.from({ length: 25 }, (_, i) => ({ trigger_event_id: String(100 - i).padStart(24, '0'), status: i === 0 ? 'running' : i === 1 ? 'failed' : 'completed', action_type: i % 2 ? 'extraction' : 'workflow', created_at: new Date(Date.UTC(2026, 8, 28, 12, 0, -i)).toISOString(), started_at: '2026-09-28T12:00:00Z', completed_at: i ? '2026-09-28T12:01:00Z' : null, error: i === 1 ? 'A source document is unavailable. Review the source before running again.' : null, output: null }))
await page.route('**/api/automations/auto-1', route => route.fulfill({ json: { ...automation, can_manage: !viewer } }))
await page.route('**/api/automations/auto-1/runs?*', route => {
  const before = new URL(route.request().url()).searchParams.get('before_id'); pageCursors.push(before)
  if (failList || (before && failPage)) return route.fulfill({ status: 503, json: { detail: 'History temporarily unavailable.' } })
  return route.fulfill({ json: { items: empty ? [] : before ? rows.slice(20) : rows.slice(0, 20), next_cursor: empty || before ? null : { before: rows[19].created_at, before_id: rows[19].trigger_event_id } } })
})
await page.route('**/api/automations/auto-1/runs/*', route => {
  const id = route.request().url().split('/').pop(); detailIds.push(id)
  if (failDetail) return route.fulfill({ status: 503, json: { detail: 'Run details temporarily unavailable.' } })
  const row = rows.find(row => row.trigger_event_id === id)
  return route.fulfill({ json: { ...row, ...(id === rows[0].trigger_event_id && complete ? { status: 'completed', completed_at: '2026-09-28T12:01:00Z', output: 'Recovered output from the existing accepted run.' } : id !== rows[0].trigger_event_id && row.status === 'completed' ? { output: 'Recorded output for ' + id } : {}) } })
})
await page.route('**/api/automations/auto-1/run-now', route => { posts++; return route.fulfill({ status: 500, json: { detail: 'History must never launch a run.' } }) })
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
async function openHistory() { await page.getByRole('button', { name: 'Run history Recorded status and results', exact: true }).click() }
try {
  for (const [width, height] of [[320, 568], [768, 700], [1440, 900]]) {
    failList = true; failPage = false; failDetail = false; complete = false; empty = false; viewer = false; posts = 0; pageCursors = []; detailIds = []
    await page.setViewportSize({ width, height }); await page.goto(review.baseURL + '/?mode=automations&automation=auto-1')
    await openHistory(); await page.getByRole('button', { name: 'Retry history', exact: true }).waitFor(); await shot('automation-history-error-' + width)
    failList = false; await page.getByRole('button', { name: 'Retry history', exact: true }).click()
    await page.getByRole('button', { name: 'Open run ' + rows[0].trigger_event_id, exact: true }).waitFor(); await shot('automation-history-list-' + width)
    failPage = true; await page.getByRole('button', { name: 'Load older runs', exact: true }).click()
    await page.getByRole('button', { name: 'Retry history', exact: true }).waitFor(); await shot('automation-history-page-error-' + width)
    failPage = false; await page.getByRole('button', { name: 'Retry history', exact: true }).click()
    const oldest = page.getByRole('button', { name: 'Open run ' + rows[24].trigger_event_id, exact: true }); await oldest.waitFor()
    assert.equal(await page.getByRole('button', { name: 'Load older runs', exact: true }).count(), 0)
    assert.deepEqual(pageCursors.slice(-2), [rows[19].trigger_event_id, rows[19].trigger_event_id])
    await oldest.focus(); await oldest.press('Enter')
    await page.getByRole('region', { name: 'Recorded run output', exact: true }).scrollIntoViewIfNeeded(); await shot('automation-history-older-output-' + width)
    await page.getByRole('button', { name: 'Close run details', exact: true }).click(); assert.equal(await oldest.evaluate(el => el === document.activeElement), true)
    failDetail = true; await page.getByRole('button', { name: 'Open run ' + rows[1].trigger_event_id, exact: true }).click()
    await page.getByRole('button', { name: 'Retry run details', exact: true }).waitFor(); await shot('automation-history-detail-error-' + width)
    failDetail = false; await page.getByRole('button', { name: 'Retry run details', exact: true }).click()
    await page.getByRole('button', { name: 'Prepare another run', exact: true }).waitFor(); await shot('automation-history-failed-result-' + width)
    await page.getByRole('button', { name: 'Prepare another run', exact: true }).click()
    await page.getByRole('region', { name: 'Run now', exact: true }).waitFor(); assert.equal(posts, 0)
    await page.getByRole('button', { name: 'Close run now', exact: true }).click()
    await page.getByRole('button', { name: 'Open run ' + rows[0].trigger_event_id, exact: true }).click()
    await page.getByText('Status: running', { exact: true }).waitFor(); await shot('automation-history-running-' + width)
    await page.getByRole('button', { name: 'Close automation', exact: true }).click()
    if (width < 768) await page.getByRole('button', { name: 'Automations panel', exact: true }).click()
    await page.getByRole('button', { name: 'Open automation: Review incoming proposals', exact: true }).click(); await openHistory()
    await page.getByRole('button', { name: 'Open run ' + rows[0].trigger_event_id, exact: true }).click()
    await page.getByText('Status: running', { exact: true }).waitFor(); complete = true
    await page.getByText('Recovered output from the existing accepted run.', { exact: true }).scrollIntoViewIfNeeded(); await shot('automation-history-recovered-' + width)
    assert.equal(detailIds.at(-1), rows[0].trigger_event_id); assert.equal(posts, 0)
    viewer = true; await page.reload(); await openHistory()
    await page.getByRole('button', { name: 'Open run ' + rows[0].trigger_event_id, exact: true }).click()
    await page.getByRole('region', { name: 'Recorded run output', exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: 'Prepare another run', exact: true }).count(), 0)
    await page.getByRole('region', { name: 'Recorded run output', exact: true }).scrollIntoViewIfNeeded()
    await shot('automation-history-reader-' + width)
    empty = true; await page.getByRole('button', { name: 'Close run details', exact: true }).click()
    await page.getByRole('button', { name: 'Refresh history', exact: true }).click()
    await page.getByText('No recorded runs yet.', { exact: true }).waitFor(); await shot('automation-history-empty-' + width)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('automation-history-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
