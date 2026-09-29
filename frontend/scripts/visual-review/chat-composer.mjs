import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page, state } = review
page.setDefaultTimeout(15000)
const models = Array.from({ length: 12 }, (_, i) => ({ tag: 'review-model-' + i, name: i === 11 ? 'A long model name for international research review with additional reasoning support' : 'Review model ' + i, context_window: 128000, tier: 'standard', speed: 'fast', privacy: 'internal', external: false }))
let failModels, emptyModels, failPreferenceRead, failPreferenceSave, failQueue, writes, queueWrites
await page.route('**/api/config/models', route => failModels ? route.fulfill({ status: 503, json: { detail: 'Models unavailable' } }) : route.fulfill({ json: emptyModels ? [] : models }))
await page.route('**/api/config/user', route => {
  if (route.request().method() === 'PUT') {
    writes.push(route.request().postDataJSON())
    return failPreferenceSave ? route.fulfill({ status: 503, json: { detail: 'Preference unavailable' } }) : route.fulfill({ json: { model: writes.at(-1).model, available_models: models } })
  }
  return failPreferenceRead ? route.fulfill({ status: 503, json: { detail: 'Preference unavailable' } }) : route.fulfill({ json: { model: models[0].tag, available_models: models, temperature: .2, top_p: 1 } })
})
await page.route('**/api/chat/queue', route => {
  queueWrites.push(route.request().postDataJSON())
  return failQueue ? route.fulfill({ status: 503, json: { detail: 'Queue temporarily unavailable.' } }) : route.fulfill({ json: { success: true } })
})
async function shot(id) {
  await review.capture(id)
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), id + ': overflow')
  assert.deepEqual(JSON.parse(await readFile(resolve(review.out, id + '.axe.json'), 'utf8')), [], id + ': accessibility')
  console.log('Captured ' + id)
}
const pickerButton = () => page.getByRole('button', { name: /^Choose chat model:/ })
const picker = () => page.getByRole('dialog', { name: 'Choose chat model', exact: true })
async function installOpenStream() {
  await page.evaluate(() => {
    const original = window.fetch.bind(window)
    window.reviewStreamRequests = []
    window.fetch = (input, init) => {
      if (new URL(typeof input === 'string' ? input : input.url, location.href).pathname !== '/api/chat') return original(input, init)
      window.reviewStreamRequests.push(JSON.parse(init.body))
      const stream = new ReadableStream({ start(controller) {
        controller.enqueue(new TextEncoder().encode(JSON.stringify({ kind: 'text', content: 'Reviewing the current sources.' }) + '\n'))
        init.signal.addEventListener('abort', () => controller.error(new DOMException('Stopped', 'AbortError')))
      } })
      return Promise.resolve(new Response(stream, { headers: { 'Content-Type': 'application/x-ndjson', 'X-Conversation-UUID': 'review-conversation', 'X-Activity-ID': 'review-activity' } }))
    }
  })
}
try {
  for (const [width, height] of [[320,568],[768,500],[1440,900]]) {
    failModels = true; emptyModels = false; failPreferenceRead = true; failPreferenceSave = true; failQueue = true; writes = []; queueWrites = []
    state.chatChunks = [{ kind: 'text', content: 'The selected model received your message.' }]
    await page.setViewportSize({ width, height }); await page.goto(review.baseURL + '/?mode=chat')
    const input = page.getByRole('textbox', { name: 'Message input' })
    await page.getByRole('button', { name: 'Retry model preference', exact: true }).waitFor()
    await input.fill('   '); assert.equal(await page.getByRole('button', { name: 'Send message', exact: true }).isDisabled(), true)
    await shot('composer-preference-load-error-' + width)
    failPreferenceRead = false; await page.getByRole('button', { name: 'Retry model preference', exact: true }).click()
    await page.getByRole('button', { name: 'Choose chat model: review-model-0', exact: true }).waitFor()
    await input.fill('Preserve this model-selection draft')
    await pickerButton().focus(); await page.keyboard.press('Enter')
    await picker().getByRole('button', { name: 'Retry models', exact: true }).waitFor(); await shot('composer-model-list-error-' + width)
    failModels = false; emptyModels = true; await picker().getByRole('button', { name: 'Retry models', exact: true }).click()
    await picker().getByRole('button', { name: 'Refresh models', exact: true }).waitFor(); await shot('composer-model-list-empty-' + width)
    emptyModels = false; await picker().getByRole('button', { name: 'Refresh models', exact: true }).click()
    await picker().getByRole('radio', { name: 'review-model-0', exact: true }).waitFor()
    await picker().getByRole('radio', { name: 'review-model-11', exact: true }).scrollIntoViewIfNeeded(); await shot('composer-model-long-list-' + width)
    for (let i = 0; i < 8; i++) { await page.keyboard.press('Tab'); assert.equal(await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]')), true) }
    await page.keyboard.press('Escape'); await picker().waitFor({ state: 'hidden' })
    assert.equal(await pickerButton().evaluate(e => e === document.activeElement), true)
    assert.equal(await input.inputValue(), 'Preserve this model-selection draft')
    await pickerButton().click(); await picker().getByRole('radio', { name: 'review-model-0', exact: true }).focus(); await page.keyboard.press('ArrowDown')
    await picker().waitFor({ state: 'hidden' }); await page.getByText('Using this model for this chat. Could not save it as your default.', { exact: false }).waitFor()
    assert.equal(writes[0].model, 'review-model-1'); await shot('composer-model-save-error-' + width)
    failPreferenceSave = false; await page.getByRole('button', { name: 'Retry model preference', exact: true }).click()
    await page.getByRole('button', { name: 'Retry model preference', exact: true }).waitFor({ state: 'hidden' }); assert.deepEqual(writes[1], writes[0])
    await input.fill('Line one'); await input.press('Shift+Enter'); await input.type('Line two')
    assert.equal(await input.inputValue(), 'Line one\nLine two')
    await input.evaluate(e => e.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, isComposing: true })))
    assert.equal(await input.inputValue(), 'Line one\nLine two')
    await input.press('Enter'); await page.getByText('The selected model received your message.', { exact: true }).waitFor()
    assert.equal(state.lastChat.model, 'review-model-1'); assert.equal(state.lastChat.message, 'Line one\nLine two')
    await shot('composer-keyboard-sent-' + width)
    await installOpenStream(); await input.fill('Continue reviewing'); await input.press('Enter')
    await page.getByRole('button', { name: 'Stop response', exact: true }).waitFor()
    await input.fill('Check the budget first.'); await page.getByRole('button', { name: 'Queue message', exact: true }).click()
    await page.getByRole('alert').filter({ hasText: 'Queue temporarily unavailable.' }).waitFor()
    assert.equal(await input.inputValue(), 'Check the budget first.'); await shot('composer-queue-error-draft-' + width)
    failQueue = false; await page.getByRole('button', { name: 'Queue message', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('textarea[aria-label="Message input"]')?.value === '')
    assert.deepEqual(queueWrites[1], queueWrites[0]); await shot('composer-queue-accepted-' + width)
    await page.getByRole('button', { name: 'Stop response', exact: true }).click()
    await page.getByRole('button', { name: 'Send message', exact: true }).waitFor()
  }
  await page.setViewportSize({ width: 320, height: 568 })
  await page.goto(review.baseURL + '/?mode=chat')
  await page.getByRole('textbox', { name: 'Message input' }).waitFor()
  await installOpenStream()
  const firstInput = page.getByRole('textbox', { name: 'Message input' })
  await firstInput.fill('Start a first response'); await firstInput.press('Enter')
  await page.getByText('Reviewing the current sources.', { exact: true }).waitFor()
  queueWrites = []
  await firstInput.fill('Keep the review concise'); await page.getByRole('button', { name: 'Queue message', exact: true }).click()
  await page.waitForFunction(() => document.querySelector('textarea[aria-label="Message input"]')?.value === '')
  assert.equal(queueWrites[0].conversation_uuid, 'review-conversation')
  await shot('composer-first-turn-queue-320')
  await page.getByRole('button', { name: 'Stop response', exact: true }).click()
  await page.getByRole('button', { name: 'Send message', exact: true }).waitFor()
  await firstInput.fill('Continue in this conversation'); await firstInput.press('Enter')
  await page.getByRole('button', { name: 'Stop response', exact: true }).waitFor()
  assert.equal(await page.evaluate(() => window.reviewStreamRequests.at(-1).activity_id), 'review-activity')
  await shot('composer-first-turn-stop-resume-320')
  await page.getByRole('button', { name: 'Stop response', exact: true }).click()
  review.observations.push('Saved-model read retry, available-model failure/empty/long-list recovery, focus containment/return, arrow selection, default-save retry without draft loss, whitespace, Enter/Shift+Enter/IME, selected model in request, touch queue failure/retained draft/retry and Stop. 320/768-short/1440; synthetic APIs/stream, no model or worker execution.')
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
} catch (error) { await review.capture('chat-composer-blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
