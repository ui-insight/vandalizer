import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { validationResult, queries } from './fixtures.mjs'

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, context, state } = review
state.validationQueries = true
page.setDefaultTimeout(10000)
let task = null, failDiscovery = false, posts = 0
const outcome = () => task && ({ task_id: task.id, status: task.status, options: task.options,
  ...(task.status === 'completed' ? { run_uuid: 'restored-result', result: validationResult } : { message: 'Waiting for a validation worker…' }) })
await context.route('**/api/knowledge/kb-1/validation-tasks/*', route => {
  if (route.request().url().endsWith('/active')) return route.fulfill(failDiscovery ? { status: 503, json: { detail: 'Unavailable' } } : { json: { task: outcome() } })
  assert.equal(route.request().url().split('/').at(-1), task.id)
  return route.fulfill({ json: outcome() })
})
await context.route('**/api/knowledge/kb-1/validate', route => {
  posts++
  const body = route.request().postDataJSON(), resumed = !!task && task.status !== 'completed'
  if (!resumed) task = { id: body.request_id, status: 'queued', options: { mode: body.mode, query_uuids: body.query_uuids, skip_judge: false } }
  return route.fulfill({ json: { task_id: task.id, status: 'queued', options: task.options, resumed } })
})
async function open(target = page) {
  await target.goto(review.baseURL + '/?mode=knowledge')
  await target.getByRole('button', { name: 'Edit', exact: true }).click()
  await target.getByRole('tab', { name: 'Validation', exact: true }).click()
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
    task = null; failDiscovery = false
    await page.setViewportSize({ width, height }); await open()
    await page.getByText('Preview selected questions (3)', { exact: true }).click()
    await page.getByRole('region', { name: 'Selected question preview' }).getByText('Expected answer: October 15', { exact: true }).waitFor()
    await shot(`validation-question-preview-${width}`, page.getByText('Preview selected questions (3)', { exact: true }))
    await page.getByRole('combobox', { name: 'Mode:', exact: true }).selectOption('judge')
    await shot(`validation-answer-only-preflight-${width}`, page.getByRole('button', { name: 'Run 3 questions', exact: true }))
    const second = await context.newPage(); await open(second)
    const before = posts
    await page.getByRole('button', { name: 'Run 3 questions', exact: true }).click()
    await page.getByText('Check queued', { exact: true }).waitFor()
    const original = task.id
    await second.getByRole('button', { name: 'Run 3 questions', exact: true }).click()
    await second.getByText('Check queued', { exact: true }).waitFor()
    assert.equal(task.id, original, 'Competing window resumes one accepted task')
    assert.equal(posts, before + 2)
    await second.close()
    await open()
    await page.getByText('Check queued', { exact: true }).waitFor()
    assert.equal(posts, before + 2, 'Reload uses GET only')
    assert.equal(await page.getByRole('combobox', { name: 'Mode:', exact: true }).inputValue(), 'judge')
    await shot(`validation-restored-running-${width}`, page.getByText('Check queued', { exact: true }))
    task.status = 'completed'; state.validated = true
    await open()
    await page.getByText('Saved run restored-result', { exact: true }).waitFor()
    assert.equal(posts, before + 2)
    await shot(`validation-restored-completion-${width}`, page.getByText('Check complete', { exact: true }))
    task = null
    await page.getByRole('tab', { name: 'Improve retrieval', exact: true }).click()
    await page.getByRole('button', { name: 'Validate & improve', exact: true }).click()
    await shot(`validation-tuning-questions-${width}`)
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await page.getByRole('region', { name: 'Questions and expectations' }).getByText('Expected answer: October 15', { exact: true }).waitFor()
    await shot(`validation-tuning-preview-${width}`)
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await page.getByText(/average answer grade on a sample/).waitFor()
    await shot(`validation-tuning-baseline-${width}`)
    await page.getByRole('button', { name: 'Next', exact: true }).click()
    await page.getByText(/Grader: Review model/).waitFor()
    await shot(`validation-tuning-budget-${width}`)
    const finalAction = page.getByRole('dialog').getByRole('button', { name: /^Validate & improve/ })
    const bounds = await finalAction.boundingBox()
    assert.ok(bounds && bounds.y >= 0 && bounds.y + bounds.height <= height, 'Final wizard action stays visible')
    await page.getByText(/Grader: Review model/).scrollIntoViewIfNeeded()
    await shot(`validation-tuning-final-review-${width}`)
  }
  task = { id: 'existing-subset', status: 'queued', options: { mode: 'judge', query_uuids: [queries[1].uuid], skip_judge: false } }
  failDiscovery = true
  await page.setViewportSize({ width: 320, height: 568 }); await open()
  await page.getByText(/We could not check for unfinished validations/).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Running…', exact: true }).isDisabled(), true)
  await shot('validation-resume-discovery-error-320', page.getByText(/We could not check for unfinished validations/))
  failDiscovery = false
  await page.getByRole('button', { name: 'Check status / reconnect', exact: true }).click()
  await page.getByText('Check queued', { exact: true }).waitFor()
  await shot('validation-restored-subset-320', page.getByText('Check queued', { exact: true }))
  review.observations.push('Reload restores exact task and completed result with no POST; competing windows converge on one synthetic accepted task. Failed discovery blocks new submissions; reconnect restores subset and mode. Full expectations, sample caveats, time, grader and cost limits reviewed at 320/768/1440px. Synthetic API fixtures; no live broker, Mongo index or model execution.')
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('validation-resumption-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
