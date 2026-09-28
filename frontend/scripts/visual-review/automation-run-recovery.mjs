import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { automation } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
let searchFailed = true, startFailed = true, statusFailed = true, status = 'failed', starts = [], checks = []
const selected = { uuid: 'doc-0', title: 'Proposal narrative with supporting evidence and budget assumptions.pdf' }
await page.route('**/api/automations', route => route.fulfill({ json: [{ ...automation, trigger_type: 'api', trigger_config: {} }] }))
await page.route('**/api/automations/auto-1', route => route.fulfill({ json: { ...automation, trigger_type: 'api', trigger_config: {} } }))
await page.route('**/api/documents/search?*', route => searchFailed
  ? route.fulfill({ status: 503, json: { detail: 'Document search temporarily unavailable.' } })
  : route.fulfill({ json: { items: new URL(route.request().url()).searchParams.get('q') === 'No matching document' ? [] : [selected], total: 1 } }))
await page.route('**/api/automations/auto-1/run-now', route => {
  starts.push(route.request().postDataJSON())
  return startFailed ? route.fulfill({ status: 503, json: { detail: 'Run could not be started.' } })
    : route.fulfill({ json: { status: 'queued', trigger_event_id: 'event-recovery', action_type: 'workflow', documents: [selected], document_source: 'chosen', documents_matched: 1 } })
})
await page.route('**/api/automations/auto-1/runs/*', route => {
  checks.push(route.request().url().split('/').pop())
  return statusFailed ? route.fulfill({ status: 503, json: { detail: 'Status service temporarily unavailable.' } })
    : route.fulfill({ json: { trigger_event_id: 'event-recovery', status, action_type: 'workflow', created_at: null, started_at: null, completed_at: null, error: status === 'failed' ? 'The document could not be reviewed.' : null, output: status === 'completed' ? 'Proposal review complete. Budget assumptions are documented.' : null } })
})
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
try {
  for (const [width, height] of [[320, 568], [768, 700], [1440, 900]]) {
    await page.evaluate(() => sessionStorage.clear()).catch(() => {})
    searchFailed = true; startFailed = true; statusFailed = true; status = 'failed'; starts = []; checks = []
    await page.setViewportSize({ width, height }); await page.goto(review.baseURL + '/?mode=automations')
    await page.getByRole('button', { name: 'Open automation: Review incoming proposals', exact: true }).click()
    await page.getByRole('button', { name: 'Run now', exact: true }).click()
    const panel = page.getByRole('region', { name: 'Run now', exact: true })
    const search = panel.getByRole('textbox', { name: 'Search documents to run with', exact: true })
    await search.fill('Proposal'); await panel.getByRole('button', { name: 'Retry document search' }).waitFor()
    await panel.getByRole('button', { name: 'Retry document search' }).scrollIntoViewIfNeeded()
    await shot('automation-run-search-error-' + width)
    searchFailed = false; await panel.getByRole('button', { name: 'Retry document search' }).click()
    const choose = panel.getByRole('button', { name: 'Choose ' + selected.title, exact: true }); await choose.waitFor()
    await choose.focus(); await choose.press('Enter')
    assert.equal(await search.inputValue(), '')
    await search.fill('No matching document')
    await panel.getByText('No documents found. Try a different search.', { exact: true }).waitFor()
    await shot('automation-run-no-results-' + width)
    await search.press('Escape')
    await panel.getByRole('button', { name: 'Run now', exact: true }).click()
    await panel.getByText('Run could not be started.', { exact: true }).waitFor()
    assert.equal(await panel.getByRole('button', { name: 'Remove ' + selected.title }).count(), 1)
    await shot('automation-run-start-error-' + width)
    startFailed = false; await panel.getByRole('button', { name: 'Reconnect run', exact: true }).click()
    await panel.getByRole('button', { name: 'Retry status check' }).waitFor()
    assert.equal(await panel.getByRole('button', { name: 'Status unavailable', exact: true }).isDisabled(), true)
    assert.equal(await search.isDisabled(), true)
    await panel.getByRole('button', { name: 'Retry status check' }).scrollIntoViewIfNeeded()
    await shot('automation-run-status-error-' + width)
    // Collapse/reopen the panel retains the accepted run and cannot enqueue it again.
    await panel.getByRole('button', { name: 'Close run now' }).click()
    await page.getByRole('button', { name: 'Run now', exact: true }).click()
    await panel.getByRole('button', { name: 'Retry status check' }).waitFor(); assert.equal(starts.length, 2)
    statusFailed = false; await panel.getByRole('button', { name: 'Retry status check' }).click()
    await panel.getByText('Run failed: The document could not be reviewed.', { exact: true }).waitFor()
    assert.deepEqual(checks, ['event-recovery', 'event-recovery']); assert.equal(starts.length, 2)
    await shot('automation-run-failed-' + width)
    status = 'completed'; await panel.getByRole('button', { name: 'Run again' }).click()
    await panel.getByText('Output', { exact: true }).click()
    await panel.getByText('Proposal review complete. Budget assumptions are documented.', { exact: true }).scrollIntoViewIfNeeded()
    await shot('automation-run-completed-' + width)
    startFailed = true; await panel.getByRole('button', { name: 'Run again' }).click()
    await panel.getByText('Run could not be started.', { exact: true }).waitFor()
    assert.equal(await panel.getByText('Proposal review complete. Budget assumptions are documented.', { exact: true }).isVisible(), true)
    await panel.getByText('Previous run', { exact: true }).waitFor()
    await panel.getByText('Proposal review complete. Budget assumptions are documented.', { exact: true }).scrollIntoViewIfNeeded()
    await shot('automation-run-retained-output-' + width)
    assert.deepEqual(starts.map(body => body.document_uuids), Array(4).fill(['doc-0']))
    assert.equal(starts[0].request_id, starts[1].request_id)
    assert.notEqual(starts[1].request_id, starts[2].request_id)
    assert.notEqual(starts[2].request_id, starts[3].request_id)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('automation-run-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
