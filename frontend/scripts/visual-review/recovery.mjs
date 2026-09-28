import assert from 'node:assert/strict'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT || '../artifacts/visual-review/recovery', baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5183' })
const { page, state } = review
page.setDefaultTimeout(9000)
async function go(path) { await page.goto(review.baseURL + path); await page.getByRole('main').waitFor(); await page.waitForTimeout(500) }
async function shot(id) { await review.capture(id); assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${id}: overflow`) }
async function send(text) { await page.getByRole('textbox', { name: 'Message input' }).fill(text); await page.getByRole('button', { name: 'Send message' }).click() }
async function installStream(chunks) {
  // Exercise the real NDJSON reader with a controlled open stream. No backend work runs.
  await page.evaluate(chunks => {
    const originalFetch = window.fetch.bind(window)
    window.fetch = (input, init) => {
      if (new URL(typeof input === 'string' ? input : input.url, location.href).pathname !== '/api/chat') return originalFetch(input, init)
      const body = new ReadableStream({ start(controller) {
        for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(JSON.stringify(chunk) + '\n'))
        init.signal.addEventListener('abort', () => controller.error(new DOMException('Stopped', 'AbortError')))
        window.failReviewStream = () => controller.error(new TypeError('Failed to fetch'))
        window.finishReviewStream = () => controller.close()
      } })
      return Promise.resolve(new Response(body, { headers: { 'Content-Type': 'application/x-ndjson', 'X-Conversation-UUID': 'review-conversation', 'X-Activity-ID': 'review-activity' } }))
    }
  }, chunks)
}
try {
  await page.setViewportSize({ width: 390, height: 700 })
  state.catalogScenario = true
  await go('/?mode=chat&tab=library')
  await page.getByRole('button', { name: 'Explore', exact: true }).click()
  await page.getByRole('button').filter({ hasText: 'Proposal readiness review' }).click()
  await shot('catalog-detail-mobile')
  await page.getByRole('button', { name: 'Save to Library', exact: true }).click()
  await page.getByRole('button', { name: 'Save', exact: true }).waitFor()
  await shot('catalog-save-destination')
  state.failCatalogSave = true
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('alert').filter({ hasText: 'Library temporarily unavailable' }).waitFor()
  await shot('catalog-save-error')
  state.failCatalogSave = false
  await page.getByRole('button', { name: 'Retry save', exact: true }).click()
  await page.getByRole('status').filter({ hasText: 'Saved to My library.' }).waitFor()
  await shot('catalog-save-success')
  await page.getByRole('button', { name: 'Done', exact: true }).click()
  await page.getByRole('button', { name: 'Save to Library', exact: true }).click()
  await page.getByText('Already saved in My library.', { exact: true }).waitFor()
  assert.equal(state.catalogSaveCalls, 2)
  await shot('catalog-already-saved')
  await page.getByRole('button', { name: 'Open workflow', exact: true }).click()
  await page.getByRole('tablist', { name: 'Workflow editor sections' }).waitFor()
  await shot('catalog-saved-item-opened')

  await go('/?mode=knowledge')
  await page.getByRole('tab', { name: 'Explore', exact: true }).click()
  await page.getByRole('button', { name: 'Research administration policies', exact: true }).click()
  state.failAdopt = true
  await page.getByRole('button', { name: 'Add to My Knowledge Bases', exact: true }).click()
  await page.getByRole('alert').filter({ hasText: 'Knowledge library temporarily unavailable' }).waitFor()
  await shot('catalog-kb-adopt-error')
  state.failAdopt = false
  await page.getByRole('button', { name: 'Add to My Knowledge Bases', exact: true }).click()
  await page.getByRole('button', { name: 'Added to My Knowledge Bases', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Added to My Knowledge Bases', exact: true }).isDisabled(), true)
  await shot('catalog-kb-adopted')

  state.optimization = true
  state.validationQueries = true
  await go('/?mode=knowledge')
  await page.getByRole('button', { name: 'Edit', exact: true }).click()
  await page.getByRole('tab', { name: 'Validation', exact: true }).click()
  await page.getByText('Composite quality: 80/100 · Proposed settings', { exact: true }).waitFor()
  await shot('validation-proposed-summary-mobile')
  await page.getByRole('tab', { name: 'Improve retrieval', exact: true }).click()
  await page.getByRole('button', { name: 'Apply optimized settings', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Apply optimized settings', exact: true }).scrollIntoViewIfNeeded()
  await shot('validation-proposed-settings-mobile')
  await page.getByRole('button', { name: 'Apply optimized settings', exact: true }).click()
  const dialog = page.getByRole('dialog')
  assert.equal(await dialog.getByRole('button', { name: 'Apply', exact: true }).isDisabled(), true)
  await shot('validation-apply-review-mobile')
  await dialog.getByRole('checkbox').check()
  state.failApply = true
  await dialog.getByRole('button', { name: 'Apply', exact: true }).click()
  await dialog.getByRole('alert').waitFor()
  await shot('validation-apply-error-mobile')
  state.failApply = false
  await dialog.getByRole('button', { name: 'Apply', exact: true }).click()
  await page.getByRole('button', { name: 'Revert', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Revert', exact: true }).scrollIntoViewIfNeeded()
  await shot('validation-applied-mobile')
  await page.getByText('Composite quality: 80/100 · Settings applied in this run', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Revert', exact: true }).click()
  await page.getByRole('button', { name: 'Apply optimized settings', exact: true }).waitFor()
  assert.equal(state.applyCalls, 2); assert.equal(state.revertCalls, 1)
  await shot('validation-reverted-mobile')
  await page.getByText('Composite quality: 80/100 · Application reverted', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Apply optimized settings', exact: true }).click()
  await page.waitForFunction(() => document.querySelector('[role=dialog] input[type=checkbox]')?.checked === false)
  assert.equal(await dialog.getByRole('button', { name: 'Apply', exact: true }).isDisabled(), true)
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()

  await go('/?mode=chat')
  await installStream([{ kind: 'plan_update', content: '', plan_tasks: [{ content: 'Create workflow', active_form: 'Creating workflow', status: 'in_progress' }] }, { kind: 'tool_call', content: '', tool_name: 'create_workflow', tool_call_id: 'unfinished', args: { name: 'Review' } }])
  await send('Create a workflow')
  await page.getByRole('button', { name: 'Stop response' }).waitFor()
  await shot('agent-running-mobile')
  await page.getByRole('button', { name: 'Stop response' }).click()
  await page.getByText(/Response stopped. Partial output is preserved/).waitFor()
  await page.getByText(/Building workflow · completion not confirmed/).waitFor()
  assert.equal(await page.locator('.animate-spin').count(), 0)
  await shot('agent-stopped-mobile')

  await go('/?mode=chat')
  await installStream([{ kind: 'tool_call', content: '', tool_name: 'create_workflow', tool_call_id: 'completed', args: { name: 'Review' } }, { kind: 'tool_result', tool_name: 'create_workflow', tool_call_id: 'completed', content: { workflow_id: 'workflow-1', name: 'Review', steps_created: 1 } }, { kind: 'tool_call', content: '', tool_name: 'run_workflow', tool_call_id: 'unfinished', args: { workflow_id: 'workflow-1' } }])
  await send('Create and run a workflow')
  await page.getByRole('button', { name: 'Stop response' }).waitFor()
  await page.evaluate(() => window.failReviewStream())
  await page.getByText(/Connection interrupted. Partial output is preserved/).waitFor()
  await page.getByRole('button', { name: 'Open workflow', exact: true }).waitFor()
  await shot('agent-partial-completion-mobile')
  await installStream([{ kind: 'text', content: 'The workflow was created. Its run status still needs checking.' }])
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await page.getByRole('button', { name: 'Stop response' }).waitFor()
  await page.evaluate(() => window.finishReviewStream())
  await page.getByRole('button', { name: 'Stop response' }).waitFor({ state: 'hidden' })
  await page.getByText('The workflow was created. Its run status still needs checking.', { exact: true }).waitFor()
  assert.equal(await page.getByText('Create and run a workflow', { exact: true }).count(), 2)
  await shot('agent-retry-preserves-context-mobile')
  await page.getByRole('button', { name: 'Open workflow', exact: true }).click()
  await page.getByRole('tablist', { name: 'Workflow editor sections' }).waitFor()
  await shot('agent-completed-artifact-opened')
} catch (error) {
  review.errors.push(String(error)); await review.capture('recovery-blocked', String(error)); process.exitCode = 1
} finally {
  await review.flush(); await review.browser.close()
  if (review.errors.length || review.unmatched.size) process.exitCode = 1
  console.log(JSON.stringify({ captures: review.captures.length, errors: review.errors, unmatched: [...review.unmatched] }, null, 2))
}
