import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { validationResult, stamp } from './fixtures.mjs'

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
state.validationQueries = true
state.validated = true // The unrelated completed run already established summary quality.
page.setDefaultTimeout(10000)
let phase = 'queued', delayed = false, failStatus = false, holdStart = false, loseStart = false, releaseStart
let taskId, completedRun
const requests = [], accepted = new Set()
const messages = {
  queued: 'Waiting for a validation worker…', running: 'Checking answers…',
  retrying: 'The worker is retrying a temporary error. No new check is needed.',
  failed: 'This check could not finish. Review your questions and sources, then start a new check.',
  unknown: 'The check’s status could not be confirmed. Check status again or review History.',
}
await page.route('**/api/knowledge/kb-1/validate', async route => {
  const body = route.request().postDataJSON(); requests.push(body); accepted.add(body.request_id); taskId = body.request_id
  if (holdStart) await new Promise(resolve => { releaseStart = resolve })
  if (loseStart) { loseStart = false; return route.fulfill({ status: 503, json: { detail: 'Simulated lost response after acceptance' } }) }
  return route.fulfill({ json: { task_id: taskId, status: 'queued' } })
})
await page.route('**/api/knowledge/kb-1/validation-tasks/*', route => {
  if (route.request().url().endsWith('/active')) return route.fulfill({ json: { task: null } })
  assert.equal(route.request().url().split('/').at(-1), taskId)
  if (failStatus) return route.fulfill({ status: 503, json: { detail: 'Status temporarily unavailable' } })
  if (phase === 'completed') return route.fulfill({ json: { task_id: taskId, status: 'completed', run_uuid: completedRun, result: validationResult } })
  return route.fulfill({ json: { task_id: taskId, status: phase, message: messages[phase], delayed } })
})
await page.route('**/api/knowledge/kb-1/quality', route => route.fulfill({ json: { history: [
  ...(phase === 'completed' ? [{ uuid: completedRun, score: 66, created_at: stamp, result_snapshot: validationResult }] : []),
  { uuid: 'unrelated-concurrent-run', score: 66, created_at: stamp, result_snapshot: validationResult },
], contract: {} } }))
async function shot(id, locator) {
  if (locator) await locator.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${id}: page overflow`)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, `${id}.axe.json`), 'utf8')), [], `${id}: axe findings`)
  console.log(`Captured ${id}`)
}
async function open() {
  await page.goto(review.baseURL + '/?mode=knowledge')
  await page.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByRole('tab', { name: 'Validation', exact: true }).click()
}
const reconnect = () => page.getByRole('button', { name: 'Check status / reconnect', exact: true }).click()
try {
  for (const [width, height] of [[320,568], [768,600], [1440,900]]) {
    phase = 'queued'; delayed = false; holdStart = true; failStatus = false
    const before = requests.length
    await page.setViewportSize({ width, height }); await open()
    await page.getByRole('button', { name: 'Run 3 questions', exact: true }).click()
    await page.getByText('Submitting check', { exact: true }).waitFor()
    await shot(`validation-task-submitting-${width}`, page.getByText('Submitting check', { exact: true }))
    holdStart = false; releaseStart()
    await page.getByText('Check queued', { exact: true }).waitFor()
    await page.getByRole('tab', { name: 'Sources (3)', exact: true }).click()
    await page.getByRole('tab', { name: 'Validation', exact: true }).click()
    assert.equal(await page.getByRole('button', { name: 'Running…', exact: true }).isDisabled(), true)
    await shot(`validation-task-queued-${width}`, page.getByText('Check queued', { exact: true }))
    phase = 'running'; await reconnect()
    await page.getByText('Checking answers…', { exact: true }).waitFor()
    await page.getByRole('tab', { name: 'History', exact: true }).click()
    await page.getByText('Checking answers…', { exact: true }).waitFor()
    await shot(`validation-task-running-history-${width}`, page.getByText('Checking answers…', { exact: true }))
    phase = 'retrying'; delayed = true; await reconnect()
    await page.getByText(messages.retrying, { exact: true }).waitFor()
    await page.getByRole('tab', { name: 'Test questions', exact: true }).click()
    await shot(`validation-task-delayed-questions-${width}`, page.getByText(messages.retrying, { exact: true }))
    await page.getByRole('tab', { name: 'Check answer quality', exact: true }).click()
    assert.equal(await page.getByRole('button', { name: 'Running…', exact: true }).isDisabled(), true)
    await shot(`validation-task-retrying-${width}`, page.getByText('Worker retrying', { exact: true }))
    failStatus = true; await reconnect()
    await page.getByText('Connection needs attention', { exact: true }).waitFor()
    await page.getByRole('tab', { name: 'History', exact: true }).click()
    await shot(`validation-task-status-error-${width}`, page.getByText(/Status is temporarily unavailable/))
    failStatus = false; phase = 'failed'; delayed = false; await reconnect()
    await page.getByText(messages.failed, { exact: true }).waitFor()
    await page.getByRole('tab', { name: 'Check answer quality', exact: true }).click()
    assert.equal(await page.getByRole('button', { name: 'Run 3 questions', exact: true }).isEnabled(), true)
    await shot(`validation-task-failed-${width}`, page.getByText('Check failed', { exact: true }))
    assert.equal(requests.length, before + 1, 'Tab switches and reconnects must not submit another check')
    const priorTask = taskId
    phase = 'queued'
    await page.getByRole('button', { name: 'Run 3 questions', exact: true }).click()
    await page.getByText('Check queued', { exact: true }).waitFor()
    assert.notEqual(taskId, priorTask, 'A deliberate new check after confirmed failure gets a new ID')
    completedRun = `saved-completion-${width}`; phase = 'completed'; await reconnect()
    await page.getByText(`Saved run ${completedRun}`, { exact: true }).waitFor()
    await shot(`validation-task-completed-${width}`, page.getByText('Check complete', { exact: true }))
  }
  await page.setViewportSize({ width: 320, height: 568 })
  phase = 'queued'; loseStart = true
  await open()
  const before = requests.length, acceptedBefore = accepted.size
  await page.getByRole('button', { name: 'Run 3 questions', exact: true }).click()
  await page.getByText(/The start response was not received/).waitFor()
  await shot('validation-task-lost-start-320', page.getByText(/The start response was not received/))
  await reconnect(); await page.getByText('Check queued', { exact: true }).waitFor()
  assert.deepEqual(requests[before], requests[before + 1], 'Lost start response retries the same request and options')
  assert.equal(accepted.size, acceptedBefore + 1, 'Idempotency fixture accepted one task')
  phase = 'unknown'; delayed = true; await reconnect()
  await page.getByText(messages.unknown, { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Running…', exact: true }).isDisabled(), true)
  await shot('validation-task-unknown-320', page.getByText(messages.unknown, { exact: true }))
  review.observations.push('Queued/running/delayed/retrying/failure/completion preserved across Sources, Validation, Test questions and History at 320/768/1440px. Reconnects submit no duplicate; lost-start retry reuses exact request ID/options. Unrelated history cannot finish the active task. Responses synthetic, not a live broker/worker test. Unknown outcome remains locked pending confirmation.')
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) {
  await review.capture('validation-task-blocked', String(error))
  throw error
} finally { await review.flush(); await review.browser.close() }
