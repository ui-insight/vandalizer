import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
import { queries } from './fixtures.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
state.validationQueries = true
page.setDefaultTimeout(10000)
let rows = structuredClone(queries), fail = '', calls = []
await page.route('**/api/knowledge/kb-1/test-queries**', route => {
  const request = route.request(), path = new URL(request.url()).pathname, method = request.method()
  if (method === 'GET') return route.fulfill({ json: { test_queries: rows } })
  calls.push({ method, path, body: request.postDataJSON() })
  if (fail === method || fail === 'import' && path.endsWith('/import')) return route.fulfill({ status: 503, json: { detail: 'Question service temporarily unavailable' } })
  if (path.endsWith('/import')) {
    rows.push({ ...queries[0], uuid: 'imported', query: 'Imported question', expected_answer: 'Imported answer', external_id: 'IMPORT-1', import_batch_label: 'questions.csv' })
    return route.fulfill({ json: { created: 1, updated: 0, skipped: 0, total_rows: 2, errors: [{ row: 3, error: 'Question is blank' }], unmatched_source_labels: [{ label: 'Unknown source', questions: 1 }] } })
  }
  if (method === 'POST') { const row = { ...queries[0], ...request.postDataJSON(), uuid: 'new-question' }; rows.push(row); return route.fulfill({ json: row }) }
  const id = path.split('/').at(-1)
  if (method === 'PATCH') { rows = rows.map(q => q.uuid === id ? { ...q, ...request.postDataJSON() } : q); return route.fulfill({ json: rows.find(q => q.uuid === id) }) }
  rows = rows.filter(q => q.uuid !== id); return route.fulfill({ json: { ok: true } })
})
async function shot(id, locator) {
  if (locator) await locator.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${id}: overflow`)
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, `${id}.axe.json`), 'utf8')), [], `${id}: accessibility`)
  console.log(`Captured ${id}`)
}
try {
  for (const [width, height] of [[320,568],[768,600],[1440,900]]) {
    rows = structuredClone(queries); fail = ''; calls = []
    await page.setViewportSize({ width, height })
    await page.goto(review.baseURL + '/?mode=knowledge')
    await page.getByRole('button', { name: 'Edit', exact: true }).click()
    await page.getByRole('tab', { name: 'Validation', exact: true }).click()
    await page.getByRole('tab', { name: 'Test questions', exact: true }).click()
    await page.getByRole('searchbox').fill('no matching question')
    await page.getByRole('button', { name: 'Add manually' }).click()
    await page.getByRole('textbox', { name: 'Query', exact: true }).fill('New question with a reviewed answer?')
    await page.getByRole('textbox', { name: 'Expected answer', exact: true }).fill('The reviewed answer with enough detail to judge.')
    fail = 'POST'; await page.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByRole('alert').filter({ hasText: 'Your draft is preserved' }).waitFor()
    await shot(`validation-question-add-error-${width}`, page.getByRole('button', { name: 'Save', exact: true }))
    fail = ''; await page.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByText('New question with a reviewed answer?', { exact: true }).waitFor()
    assert.equal(await page.getByRole('searchbox').inputValue(), '')
    await page.getByRole('checkbox', { name: 'Select test query: New question with a reviewed answer?', exact: true }).check()
    await page.getByRole('button', { name: 'Edit test query', exact: true }).last().click()
    await page.getByRole('textbox', { name: 'Expected answer', exact: true }).fill('Corrected expected answer')
    fail = 'PATCH'; await page.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByRole('alert').filter({ hasText: 'Your edits are preserved' }).waitFor()
    await shot(`validation-question-edit-error-${width}`, page.getByRole('textbox', { name: 'Expected answer', exact: true }))
    fail = ''; await page.getByRole('button', { name: 'Save', exact: true }).click()
    await page.getByText('Corrected expected answer', { exact: false }).waitFor()
    await page.getByRole('button', { name: 'Run selected (1)', exact: true }).click()
    await page.getByText('Preview selected questions (1)', { exact: true }).click()
    await page.getByRole('region', { name: 'Selected question preview' }).getByText('Expected answer: Corrected expected answer', { exact: true }).waitFor()
    await shot(`validation-question-selected-scope-${width}`, page.getByRole('button', { name: 'Run 1 question', exact: true }))
    await page.getByRole('tab', { name: 'Test questions', exact: true }).click()
    fail = 'DELETE'; await page.getByRole('button', { name: 'Delete test query', exact: true }).last().click()
    await page.getByRole('dialog').getByRole('button', { name: 'Confirm', exact: true }).click()
    await page.getByRole('alert').filter({ hasText: 'Could not delete' }).waitFor()
    await shot(`validation-question-delete-error-${width}`, page.getByRole('alert').filter({ hasText: 'Could not delete' }))
    fail = ''; await page.getByRole('button', { name: 'Delete test query', exact: true }).last().click()
    await page.getByRole('dialog').getByRole('button', { name: 'Confirm', exact: true }).click()
    await page.getByText('New question with a reviewed answer?', { exact: true }).waitFor({ state: 'hidden' })
    await page.getByRole('button', { name: 'Import CSV/Excel' }).click()
    const dialog = page.getByRole('dialog', { name: 'Import test queries' })
    await dialog.locator('input[type=file]').setInputFiles({ name: 'questions.txt', mimeType: 'text/plain', buffer: Buffer.from('bad') })
    await dialog.getByRole('alert').waitFor()
    await shot(`validation-question-import-format-${width}`, dialog.getByRole('alert'))
    await dialog.locator('input[type=file]').setInputFiles({ name: 'questions.csv', mimeType: 'text/csv', buffer: Buffer.from('Question,Expected Answer\nImported question,Imported answer\n,Blank') })
    fail = 'import'; await dialog.getByRole('button', { name: 'Import', exact: true }).click()
    await dialog.getByRole('alert').waitFor()
    await shot(`validation-question-import-error-${width}`, dialog.getByRole('button', { name: 'Import', exact: true }))
    fail = ''; await dialog.getByRole('button', { name: 'Import', exact: true }).click()
    await dialog.getByRole('status').waitFor()
    await shot(`validation-question-import-partial-${width}`, dialog.getByRole('button', { name: 'Done', exact: true }))
    assert.equal(await dialog.getByRole('button', { name: 'Import complete' }).isDisabled(), true)
    await dialog.getByRole('button', { name: 'Done', exact: true }).click()
    await page.getByRole('checkbox', { name: 'Select test query: Imported question', exact: true }).waitFor()
    assert.ok(calls.every(c => c.path.startsWith('/api/knowledge/kb-1/test-queries')), 'Mutations stay on the selected KB')
  }
  rows = Array.from({ length: 251 }, (_, i) => ({ ...queries[0], uuid: `large-${i}`, query: `Question ${i}: ${'a long source-specific question '.repeat(3)}`, expected_answer: 'A reviewed reference answer. '.repeat(8) }))
  await page.setViewportSize({ width: 320, height: 568 })
  await page.goto(review.baseURL + '/?mode=knowledge')
  await page.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByRole('tab', { name: 'Validation', exact: true }).click()
  await page.getByRole('tab', { name: 'Test questions', exact: true }).click()
  await page.getByText('Showing 50 of 251 matching questions. Select all includes every matching question.').waitFor()
  assert.equal(await page.getByRole('button', { name: 'Edit test query', exact: true }).count(), 50)
  await page.getByRole('checkbox', { name: 'Select all all test queries' }).check()
  await page.getByRole('button', { name: 'Run selected (251)' }).waitFor()
  await page.getByRole('searchbox').fill('Question 250:')
  assert.equal(await page.getByRole('checkbox', { name: /^Select test query: Question 250:/ }).isChecked(), true)
  await shot('validation-question-large-set-selection-320', page.getByRole('searchbox'))
  await page.getByRole('button', { name: 'Run selected (251)' }).click()
  await page.getByText('Preview selected questions (251)', { exact: true }).click()
  await page.getByRole('button', { name: 'Show all 251 questions' }).waitFor()
  await shot('validation-question-large-set-preview-320', page.getByText('Preview selected questions (251)', { exact: true }))
  review.observations.push('Question add/edit/delete failures preserve drafts/selection, successful creation clears stale search, selected-run preview preserves exact edited scope. Import rejects unsupported extension, retries preserved file and displays row errors plus unmatched source labels; completed import cannot be resubmitted. 320/768/1440px; fixtures only.')
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('validation-questions-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
