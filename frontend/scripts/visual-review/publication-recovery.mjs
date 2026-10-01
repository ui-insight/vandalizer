import assert from 'node:assert/strict'
import { expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(15000)
let fail = true, requests = []
await page.route('**/api/verification/submit', async route => {
  requests.push(route.request().postDataJSON())
  await new Promise(resolve => setTimeout(resolve, 450))
  return fail ? route.fulfill({ status: 503, json: { detail: 'Submission unavailable. Your draft is retained.' } }) : route.fulfill({ json: { uuid: 'synthetic-submission', status: 'pending' } })
})
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
const details = {
  'Run Instructions': 'Select one sponsor notice, run the review, then inspect each deadline against its cited passage.',
  'Evaluation Notes': 'Confirm all dates against the original notice.',
  'Known Limitations': 'Scanned tables may be incomplete. A research administrator must check the source.',
  'Dependencies': 'Access to the selected sponsor notice',
  'Example Inputs': 'Synthetic sponsor notice: application due October 15.',
  'Expected Outputs': 'Deadline checklist: October 15, with a source citation.',
  'Intended Use Tags': 'research-admin\nproposal-review',
}
try {
  for (const width of [320, 1440]) {
    fail = true; requests = []
    await page.setViewportSize({ width, height: width === 320 ? 640 : 1000 })
    await page.goto(review.baseURL + '/?mode=chat&tab=library')
    const row = page.locator('.library-item-row').filter({ has: page.getByRole('button', { name: 'Open Proposal readiness review', exact: true }) })
    await row.hover()
    await row.getByRole('button', { name: 'More actions', exact: true }).click()
    await page.getByRole('button', { name: 'Share with everyone', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: 'Share with everyone', exact: true })
    await shot('publication-intent-' + width)
    await dialog.getByRole('button', { name: /Share with everyone — it works for me/ }).click()
    await dialog.getByRole('textbox', { name: 'Summary', exact: false }).fill('Check sponsor deadlines')
    await dialog.getByRole('textbox', { name: 'Description', exact: true }).fill('Review one sponsor notice and produce a cited deadline checklist for proposal preparation.')
    await dialog.getByRole('combobox', { name: 'Category', exact: true }).selectOption('Research Administration')
    await dialog.getByRole('textbox', { name: 'Your Organization', exact: true }).fill('Synthetic Research Office')
    await shot('publication-task-input-deliverable-' + width)
    await dialog.getByRole('button', { name: 'Next', exact: true }).click()
    for (const [name, value] of Object.entries(details)) await dialog.getByRole('textbox', { name, exact: true }).fill(value)
    await dialog.getByRole('textbox', { name: 'Example Inputs', exact: true }).scrollIntoViewIfNeeded()
    await shot('publication-examples-' + width)
    await dialog.getByRole('button', { name: 'Next', exact: true }).click()
    for (const name of ['Example Inputs', 'Expected Outputs', 'Dependencies']) await dialog.getByText(details[name], { exact: true }).waitFor()
    await dialog.getByText(details['Example Inputs'], { exact: true }).scrollIntoViewIfNeeded()
    assert.ok(await dialog.getByText(details['Example Inputs'], { exact: true }).evaluate(element => { const box = element.getBoundingClientRect(); const footer = element.closest('[role=dialog]').lastElementChild.getBoundingClientRect(); return box.bottom <= footer.top }), 'Review content must remain above its fixed footer')
    await shot('publication-review-full-values-' + width)
    const submit = dialog.getByRole('button', { name: 'Share with everyone', exact: true })
    await submit.click()
    await expect(dialog.getByRole('button', { name: 'Sending...', exact: true })).toBeDisabled()
    await page.keyboard.press('Escape'); await expect(dialog).toBeVisible()
    const error = dialog.getByRole('alert'); await error.waitFor(); await expect(error).toBeFocused()
    assert.equal(requests.length, 1)
    await shot('publication-submit-error-' + width)
    await dialog.getByRole('button', { name: 'Back', exact: true }).click()
    for (const [name, value] of Object.entries(details)) assert.equal(await dialog.getByRole('textbox', { name, exact: true }).inputValue(), value)
    await dialog.getByRole('button', { name: 'Next', exact: true }).click(); fail = false; await submit.click()
    await dialog.waitFor({ state: 'hidden' })
    assert.equal(requests.length, 2); assert.deepEqual(requests[1], requests[0]); assert.equal(requests[0].skip_validation, false)
    assert.deepEqual(requests[0].expected_outputs, [details['Expected Outputs']]); assert.deepEqual(requests[0].example_inputs, [details['Example Inputs']])
    await shot('publication-submitted-' + width)
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push('Author task/input/deliverable/example guidance, complete review values, guarded pending submission, failed draft retention and identical retry at 320/1440. Synthetic intercepted submissions only; no item published or examiner contacted.')
} catch (error) { await review.capture('publication-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
