import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { automation } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
let starts = [], receipts = new Map(), status = 'running', loseResponse = true, pending = false, reject = false
await page.route('**/api/automations', route => route.fulfill({ json: [automation] }))
await page.route('**/api/automations/auto-1', route => route.fulfill({ json: automation }))
await page.route('**/api/automations/auto-1/run-now', route => {
  const body = route.request().postDataJSON(); starts.push(body)
  assert.match(body.request_id, /^[0-9a-f-]{36}$/)
  if (reject) return route.fulfill({ status: 400, json: { detail: 'No documents match the configured filters.' } })
  if (!receipts.has(body.request_id)) receipts.set(body.request_id, 'event-' + receipts.size)
  if (pending) return route.fulfill({ status: 409, json: { detail: 'Launch outcome is not yet confirmed.' } })
  if (loseResponse) { loseResponse = false; return route.fulfill({ status: 503, json: { detail: 'Launch response unavailable.' } }) }
  return route.fulfill({ json: { status: 'queued', trigger_event_id: receipts.get(body.request_id), action_type: 'workflow', documents: [{ uuid: 'doc-0', title: 'Proposal narrative.pdf' }], document_source: 'folder', documents_matched: 1 } })
})
await page.route('**/api/automations/auto-1/runs/*', route => route.fulfill({ json: { trigger_event_id: route.request().url().split('/').pop(), status, action_type: 'workflow', created_at: null, started_at: null, completed_at: null, error: null, output: status === 'completed' ? 'Proposal reviewed.' : null } }))
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
async function open() {
  const row = page.getByRole('button', { name: 'Open automation: ' + automation.name, exact: true })
  const editor = page.getByRole('button', { name: 'Rename automation', exact: true })
  await row.or(editor).first().waitFor()
  if (!await editor.isVisible()) await row.click()
  await page.getByRole('button', { name: 'Run now', exact: true }).click()
}
try {
  for (const [width, height] of [[320, 568], [768, 700], [1440, 900]]) {
    starts = []; receipts = new Map(); status = 'running'; loseResponse = true; pending = false; reject = false
    await page.setViewportSize({ width, height }); await page.goto(review.baseURL + '/?mode=automations')
    await open()
    const panel = page.getByRole('region', { name: 'Run now', exact: true })
    await panel.getByRole('button', { name: 'Run now', exact: true }).click()
    await panel.getByRole('button', { name: 'Reconnect run' }).scrollIntoViewIfNeeded()
    await shot('automation-launch-lost-response-' + width)
    assert.equal(receipts.size, 1)
    await page.reload(); await open()
    await panel.getByRole('button', { name: 'Reconnect run' }).scrollIntoViewIfNeeded()
    assert.equal(starts.length, 1)
    await shot('automation-launch-reloaded-' + width)
    pending = true; await panel.getByRole('button', { name: 'Reconnect run' }).click()
    await panel.getByText('Launch outcome is not yet confirmed.', { exact: true }).waitFor()
    await panel.getByRole('button', { name: 'Reconnect run' }).scrollIntoViewIfNeeded()
    await shot('automation-launch-unconfirmed-' + width)
    pending = false; await panel.getByRole('button', { name: 'Reconnect run' }).click()
    await panel.getByRole('button', { name: 'Running…', exact: true }).waitFor()
    assert.equal(receipts.size, 1); assert.deepEqual(starts, Array(3).fill(starts[0]))
    await panel.getByRole('button', { name: 'Running…', exact: true }).scrollIntoViewIfNeeded()
    await shot('automation-launch-reconnected-' + width)
    await page.getByRole('button', { name: 'Close automation', exact: true }).click()
    if (width < 768) await page.getByRole('button', { name: 'Automations panel', exact: true }).click()
    await open()
    await panel.getByRole('button', { name: 'Reconnect run' }).click()
    await panel.getByRole('button', { name: 'Running…', exact: true }).waitFor()
    assert.equal(receipts.size, 1); assert.equal(starts.length, 4)
    assert.equal(starts[3].request_id, starts[0].request_id)
    status = 'completed'
    await panel.getByRole('button', { name: 'Run again', exact: true }).waitFor()
    await panel.getByText(/This status does not confirm delivery/).scrollIntoViewIfNeeded()
    await shot('automation-launch-completed-' + width)
    reject = true; await panel.getByRole('button', { name: 'Run again' }).click()
    await panel.getByText('No documents match the configured filters.', { exact: true }).waitFor()
    assert.equal(await panel.getByRole('button', { name: 'Reconnect run' }).count(), 0)
    assert.notEqual(starts[4].request_id, starts[0].request_id)
    await panel.getByText('No documents match the configured filters.', { exact: true }).scrollIntoViewIfNeeded()
    await shot('automation-launch-validation-error-' + width)
    assert.equal(receipts.size, 1)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('automation-launch-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
