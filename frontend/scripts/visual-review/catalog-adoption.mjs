import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { items, workflow } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
let saved, failSave, failSource, failCopy, version, writes, copies
const shared = () => ({ ...workflow, verified: true, can_manage: false, description: 'Published instructions version ' + version, steps: [{ id: 'step-1', name: 'Check sponsor requirements', is_output: true, data: {}, tasks: [{ id: 'task-1', name: 'Prompt', data: { prompt: 'Review the source.' } }] }] })
await page.route('**/api/library?*', r => r.fulfill({ json: [{ id: 'library-1', scope: 'personal', title: 'My library', owner_user_id: 'reviewer' }, { id: 'team-library', scope: 'team', team_id: 'team-1', title: 'Research office' }] }))
for (const id of ['library-1', 'team-library']) await page.route('**/api/library/' + id + '/items*', r => {
  if (r.request().method() === 'POST') {
    writes.push({ library: id, body: r.request().postDataJSON() })
    if (failSave) return r.fulfill({ status: 503, json: { detail: 'Destination unavailable. Try again.' } })
    saved.add(id); return r.fulfill({ json: { ...items[0], verified: true } })
  }
  return r.fulfill({ json: saved.has(id) ? [{ ...items[0], verified: true }] : [] })
})
await page.route('**/api/workflows/workflow-1', r => failSource ? r.fulfill({ status: 404, json: { detail: 'Shared source unavailable.' } }) : r.fulfill({ json: shared() }))
await page.route('**/api/workflows/workflow-1/duplicate*', r => { copies++; return failCopy ? r.fulfill({ status: 503, json: { detail: 'Copy service unavailable.' } }) : r.fulfill({ json: { ...workflow, id: 'editable-copy', uuid: 'editable-copy' } }) })
await page.route('**/api/workflows/editable-copy', r => r.fulfill({ json: { ...shared(), id: 'editable-copy', uuid: 'editable-copy', name: 'Proposal readiness review (Copy)', can_manage: true, verified: false } }))
await page.route('**/api/workflows/editable-copy/history*', r => r.fulfill({ json: { runs: [] } }))
await page.route('**/api/workflows/editable-copy/quality-sparkline*', r => r.fulfill({ json: { scores: [] } }))
await page.route('**/api/workflows/editable-copy/quality-status*', r => r.fulfill({ json: {} }))
async function shot(id) { await review.capture(id); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow'); assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility'); console.log('Captured ' + id) }
async function catalogDetail() { await page.goto(review.baseURL + '/?mode=chat&tab=library'); await page.getByRole('button', { name: 'Explore', exact: true }).click(); await page.getByRole('button', { name: workflow.name, exact: true }).click() }
try {
  for (const width of [320, 1440]) {
    saved = new Set(); failSave = true; failSource = false; failCopy = true; version = 1; writes = []; copies = 0
    await page.setViewportSize({ width, height: width === 320 ? 700 : 1000 }); await catalogDetail()
    await page.getByRole('button', { name: 'Save to Library', exact: true }).click()
    const save = page.getByRole('dialog', { name: 'Save to Library', exact: true }); await save.getByText(/Save a reference to this shared item/).waitFor()
    await save.getByRole('button', { name: 'Save', exact: true }).click(); await save.getByRole('alert').waitFor(); await shot('catalog-save-error-' + width)
    failSave = false; await save.getByRole('button', { name: 'Retry save', exact: true }).click(); await save.getByText('Saved to My library.', { exact: true }).waitFor()
    await save.getByRole('button', { name: 'Done', exact: true }).click(); await page.getByRole('button', { name: 'Save to Library', exact: true }).click(); await save.getByText('Already saved in My library.', { exact: true }).waitFor(); assert.equal(writes.length, 2)
    await save.getByRole('combobox', { name: 'Destination library', exact: false }).selectOption('team-library'); await save.getByRole('button', { name: 'Save', exact: true }).click(); await save.getByText('Saved to Research office.', { exact: true }).waitFor(); await shot('catalog-team-reference-' + width)
    await save.getByRole('button', { name: 'Open workflow', exact: true }).click(); await page.getByText(/This shared workflow is view-only/).waitFor(); await page.getByText('Published instructions version 1', { exact: true }).waitFor(); await shot('catalog-view-only-source-' + width)
    await page.getByRole('button', { name: 'Close workflow', exact: true }).click(); await page.getByRole('button', { name: 'Mine', exact: true }).click(); await page.getByText('Saved reference · Shared with everyone', { exact: true }).waitFor(); await shot('catalog-reference-in-mine-' + width)
    version = 2; await page.getByRole('button', { name: 'Open ' + workflow.name, exact: true }).click(); await page.getByText('Published instructions version 2', { exact: true }).waitFor(); await shot('catalog-reference-updated-source-' + width)
    await page.getByRole('button', { name: 'Save a copy to Team Library', exact: true }).click(); await page.getByText('Copy service unavailable.', { exact: true }).waitFor(); await page.getByText(/This shared workflow is view-only/).waitFor(); await shot('catalog-copy-error-' + width)
    failCopy = false; await page.getByRole('button', { name: 'Save a copy to Team Library', exact: true }).click(); await page.getByText('Proposal readiness review (Copy)', { exact: true }).waitFor(); assert.equal(copies, 2); await shot('catalog-editable-copy-' + width)
    failSource = true; await page.goto(review.baseURL + '/?mode=chat&tab=library&workflow=workflow-1'); await page.getByRole('button', { name: 'Retry workflow', exact: true }).waitFor(); await shot('catalog-source-unavailable-' + width)
    failSource = false; await page.getByRole('button', { name: 'Retry workflow', exact: true }).click(); await page.getByText('Published instructions version 2', { exact: true }).waitFor()
    assert.deepEqual(writes, [{ library: 'library-1', body: { item_id: 'workflow-1', kind: 'workflow' } }, { library: 'library-1', body: { item_id: 'workflow-1', kind: 'workflow' } }, { library: 'team-library', body: { item_id: 'workflow-1', kind: 'workflow' } }])
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push('Synthetic saved references in personal/team destinations, failed-save retry/idempotent reopen, view-only shared workflow, refreshed source revision, failed/successful independent copy and unavailable source retry. Backend source review establishes pointer versus copied object semantics; this is frontend behavior, not live persistence evidence.')
} catch (error) { await review.capture('catalog-adoption-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
